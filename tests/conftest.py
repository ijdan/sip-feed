"""Fixtures partagées pour les tests fonctionnels Sip-feed."""
import os
import sys
import jwt
import datetime
import pytest
from pathlib import Path

# Chemins
ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV = ROOT / "backend" / ".env"

# URLs
BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# Charge le JWT_SECRET depuis le .env backend
def _load_env():
    env = {}
    if BACKEND_ENV.exists():
        for line in BACKEND_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

_env = _load_env()
JWT_SECRET = _env.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"


def make_token(email: str, role: str = "reader", internal_id: str = "test_id") -> str:
    """Génère un JWT valide pour les tests."""
    payload = {
        "sub": internal_id,
        "email": email,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture(scope="session")
def admin_token():
    return make_token("telegraphroad.dummy@gmail.com", role="admin", internal_id="admin_test")


@pytest.fixture(scope="session")
def reader_token():
    return make_token("reader@test.com", role="reader", internal_id="reader_test")


@pytest.fixture(scope="session")
def api_url():
    return BASE_URL


@pytest.fixture(scope="session")
def frontend_url():
    return FRONTEND_URL
