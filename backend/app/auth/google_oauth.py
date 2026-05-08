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


def create_jwt(user_id: str, email: str, role: str = "reader") -> str:
    payload = {
        "sub": user_id,
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


@router.post("/google")
async def google_login(token: dict):
    """Reçoit un id_token Google depuis le frontend et retourne un JWT applicatif."""
    try:
        id_info = id_token.verify_oauth2_token(
            token["credential"],
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Google invalide")

    user_id = id_info["sub"]
    email = id_info["email"]

    db = get_db()
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        user_ref.set({
            "email": email,
            "role": "reader",
            "created_at": datetime.utcnow().isoformat(),
        })
        role = "reader"
    else:
        role = user_doc.to_dict().get("role", "reader")

    jwt_token = create_jwt(user_id, email, role)
    return {"access_token": jwt_token, "role": role}
