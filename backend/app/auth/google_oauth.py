import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import jwt
from datetime import datetime, timedelta

from app.config import settings
from app.db.firestore import get_db

router = APIRouter()
bearer_scheme = HTTPBearer()


def _make_internal_id() -> str:
    return "usr_" + uuid.uuid4().hex[:12]


def create_jwt(internal_id: str, email: str, role: str = "reader") -> str:
    payload = {
        "sub": internal_id,   # identifiant interne stable
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")


def require_admin(current_user: dict = Depends(verify_jwt)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès admin requis")
    return current_user


def _upsert_user(email: str, name: str, avatar: str, provider: str) -> tuple[str, str]:
    """Crée ou met à jour un utilisateur. Retourne (internal_id, role)."""
    db = get_db()
    user_ref = db.collection("users").document(email)
    user_doc = user_ref.get()
    if not user_doc.exists:
        internal_id = _make_internal_id()
        user_ref.set({
            "internal_id": internal_id, "email": email, "name": name,
            "avatar": avatar, "role": "reader", "provider": provider,
            "created_at": datetime.utcnow().isoformat(),
        })
        return internal_id, "reader"
    data = user_doc.to_dict()
    internal_id = data.get("internal_id") or _make_internal_id()
    role = data.get("role", "reader")
    updates: dict = {}
    if not data.get("internal_id"): updates["internal_id"] = internal_id
    if name and data.get("name") != name: updates["name"] = name
    if avatar and data.get("avatar") != avatar: updates["avatar"] = avatar
    if updates: user_ref.update(updates)
    return internal_id, role


@router.post("/session")
async def session_login(payload: dict):
    """Endpoint générique : reçoit email/name/avatar/provider depuis NextAuth."""
    email = payload.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email requis")
    internal_id, role = _upsert_user(
        email, payload.get("name", ""), payload.get("avatar", ""), payload.get("provider", "unknown")
    )
    return {"access_token": create_jwt(internal_id, email, role), "role": role}


@router.post("/google")
async def google_login(token: dict):
    """Reçoit un id_token Google, crée ou met à jour l'utilisateur (clé = email)."""
    try:
        id_info = id_token.verify_oauth2_token(
            token["credential"],
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Google invalide")

    email = id_info["email"]
    internal_id, role = _upsert_user(
        email, id_info.get("name", ""), id_info.get("picture", ""), "google"
    )
    return {"access_token": create_jwt(internal_id, email, role), "role": role}
