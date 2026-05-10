from fastapi import APIRouter, Depends, HTTPException
from app.auth.google_oauth import verify_jwt
from app.db.firestore import get_db
from app.models.user import User, UserUpdate, UserPreferences

router = APIRouter()


def _get_user_ref(email: str):
    return get_db().collection("users").document(email)

def _get_prefs_ref(email: str):
    return get_db().collection("user_preferences").document(email)


@router.get("/me", response_model=User)
def get_profile(current_user: dict = Depends(verify_jwt)):
    email = current_user["email"]
    doc = _get_user_ref(email).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return User(**doc.to_dict())


@router.patch("/me", response_model=User)
def update_profile(payload: UserUpdate, current_user: dict = Depends(verify_jwt)):
    email = current_user["email"]
    ref = _get_user_ref(email)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        ref.update(updates)
    doc = ref.get()
    return User(**doc.to_dict())


@router.get("/me/preferences", response_model=UserPreferences)
def get_preferences(current_user: dict = Depends(verify_jwt)):
    email = current_user["email"]
    doc = _get_prefs_ref(email).get()
    if not doc.exists:
        return UserPreferences()
    return UserPreferences(**doc.to_dict())


@router.put("/me/preferences", response_model=UserPreferences)
def update_preferences(payload: UserPreferences, current_user: dict = Depends(verify_jwt)):
    email = current_user["email"]
    _get_prefs_ref(email).set(payload.model_dump())
    return payload
