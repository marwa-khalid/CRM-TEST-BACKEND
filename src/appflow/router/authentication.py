# appflow/router/authentication.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from appflow.services.authentication_service import verify_user, register_user, reset_password
from appflow.models.authentication import LoginRequest, RegisterRequest
from libdata.settings import get_session
from libauth.auth import oauth2_scheme
from appflow.services.authentication_service import save_questionnaire

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_session)):
    user = register_user(payload.user_name, db)

    if not user["success"]:
        raise HTTPException(
            status_code=user.get("status", 400),
            detail=user["message"]
        )

    return user

@router.post("/reset-password")
def reset_password_endpoint(payload:LoginRequest, db: Session = Depends(get_session)):
    result = reset_password(payload.user_name,payload.password, db)

    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])

    return result
@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_session)):
    token = verify_user(payload, db)
    if not token:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    return token


@router.post("/save-questionnaire")
async def save_questionnaire_by_link(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session)
):
    save_questionnaire(token, db)