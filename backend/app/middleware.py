import asyncio
from datetime import date
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import jwt

from app.config import settings


def _extract_identifier(request: Request) -> str:
    """Retourne l'email de l'utilisateur ou l'IP du visiteur."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            return payload.get("email", "inconnu")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass  # Token invalide ou expiré → visiteur anonyme
    # Visiteur non authentifié : IP
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    return f"ip:{ip.split(',')[0].strip()}"


async def _log_call(identifier: str):
    """Incrémente le compteur dans Firestore (arrière-plan, non-bloquant)."""
    try:
        from app.db.firestore import get_db
        today = date.today().isoformat()
        ref = get_db().collection("api_stats").document(today)
        # Firestore n'a pas d'incrément natif via Python SDK sans transaction
        # On lit + écrit (acceptable pour des stats approximatives)
        doc = ref.get()
        counts = doc.to_dict() if doc.exists else {}
        counts[identifier] = counts.get(identifier, 0) + 1
        ref.set(counts)
    except (ConnectionError, TimeoutError, OSError):
        pass  # Erreurs réseau/Firestore transitoires — les stats ne bloquent pas
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"Stats tracking skipped: {e}")


class StatsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Tracker uniquement les appels /articles/ (GET)
        if request.method == "GET" and request.url.path.startswith("/articles"):
            identifier = _extract_identifier(request)
            asyncio.create_task(_log_call(identifier))
        return response
