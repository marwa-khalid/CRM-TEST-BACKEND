import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from appflow.services.authentication_service import (
    verify_user,
    reset_password,
    save_questionnaire,
    invite_user,
    send_login_otp,
    verify_login_otp,
    forgot_password,
)
from appflow.models.authentication import (
    LoginRequest,
    InviteUserRequest,
    SendOtpRequest,
    VerifyOtpRequest,
)
from libdata.settings import get_session
from libdata.models.tables import User
from libauth.auth import oauth2_scheme, authenticate
from libauth.token_util import sign_jwt

router = APIRouter(prefix="/auth", tags=["Auth"])

# 1 year — matches the existing (non-expiring) token lifetime.
_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


# Cross-site production (Netlify SPA served over https, or an API on a different
# site) needs SameSite=None + Secure for the cookie to be accepted. But over plain
# http://localhost a Secure cookie is dropped by the browser (Safari especially),
# so local dev overrides via env:  COOKIE_SECURE=false  COOKIE_SAMESITE=lax
_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() not in ("false", "0", "no")
_COOKIE_SAMESITE = (os.getenv("COOKIE_SAMESITE", "none").strip().lower() or "none")


def _set_auth_cookie(response: Response, token: str) -> None:
    """Store the JWT in an httpOnly cookie so JS (and XSS) can't read it."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    # delete_cookie must use the same attributes the cookie was set with.
    response.delete_cookie(
        "access_token", path="/", samesite=_COOKIE_SAMESITE, secure=_COOKIE_SECURE
    )


@router.post("/invite-user")
def invite_user_endpoint(payload: InviteUserRequest, db: Session = Depends(get_session)):
    result = invite_user(payload.user_name, db)
    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])
    return result


@router.post("/reset-password")
def reset_password_endpoint(payload: LoginRequest, db: Session = Depends(get_session)):
    result = reset_password(payload.user_name, payload.password, db)

    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])

    return result


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_session)):
    token = verify_user(payload, db)
    if not token:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    _set_auth_cookie(response, token["access_token"])
    return token


@router.post("/send-otp")
def send_otp_endpoint(payload: SendOtpRequest, db: Session = Depends(get_session)):
    result = send_login_otp(payload.user_name, db)
    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])
    return result


@router.post("/verify-otp")
def verify_otp_endpoint(
    payload: VerifyOtpRequest,
    response: Response,
    db: Session = Depends(get_session),
):
    result = verify_login_otp(payload.user_name, payload.otp)
    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])

    # OTP confirmed → issue the session token and set it as an httpOnly cookie.
    email = payload.user_name.lower().strip()
    user = db.query(User).filter(User.user_name == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    token = sign_jwt({"sub": user.user_name, "user_id": user.id, "tenant_id": user.tenant_id})
    _set_auth_cookie(response, token["access_token"])
    return {
        **result,
        **token,
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.user_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


@router.get("/me")
def get_me(request: Request, _=Depends(authenticate), db: Session = Depends(get_session)):
    """Identity for the logged-in user (from the token/cookie). name = email-before-@."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    email = user.user_name or ""
    name = email.split("@")[0] if "@" in email else email
    return {
        "id": user.id,
        "email": email,
        "name": name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "tenant_id": user.tenant_id,
    }


@router.post("/logout")
def logout(response: Response):
    _clear_auth_cookie(response)
    return {"success": True, "message": "Logged out"}


@router.post("/forgot-password")
def forgot_password_endpoint(payload: SendOtpRequest, db: Session = Depends(get_session)):
    result = forgot_password(payload.user_name, db)
    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])
    return result


@router.post("/save-questionnaire")
async def save_questionnaire_by_link(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session)
):
    result = save_questionnaire(token, db)

    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])

    return result