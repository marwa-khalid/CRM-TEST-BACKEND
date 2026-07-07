from fastapi import HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from appflow.logger import logger
from .token_util import decode_auth_token
from libdata.settings import get_session
from libdata.models.tables import UserSession

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/verify", auto_error=False)


async def authenticate(
    request: Request,
    auth_token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session),
):
    # Prefer the Authorization header; fall back to the httpOnly cookie so the
    # access token never has to live in browser-readable storage (XSS-safe).
    if not auth_token:
        auth_token = request.cookies.get("access_token")

    user_details = decode_auth_token(auth_token)
    logger.info(f'user_details: {user_details}')
    if not user_details:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    user_id = user_details.get('user_id')
    request.state.user_id = user_id
    request.state.tenant_id = user_details.get('tenant_id')
    request.state.user_name = user_details.get('user_name')

    # Validate session is still active.
    # Exempt POST /account/sessions so the registration call itself can succeed
    # even when the session doesn't exist yet in the DB.
    is_session_registration = (
        request.url.path.rstrip("/") == "/account/sessions"
        and request.method == "POST"
    )
    user_agent = request.headers.get("user-agent", "")
    if user_id and user_agent and not is_session_registration:
        has_any = db.query(UserSession.id).filter(
            UserSession.user_id == user_id,
        ).first()
        if has_any:
            active = db.query(UserSession.id).filter(
                UserSession.user_id == user_id,
                UserSession.device_info == user_agent,
                UserSession.is_deleted == False,
                UserSession.is_active == True,
            ).first()
            if not active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session terminated. Please log in again.",
                )

    return user_details
