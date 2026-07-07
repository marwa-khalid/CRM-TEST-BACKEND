from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from libdata.settings import get_session
from appflow.models.account_settings import (
    ChangePasswordRequest,
    RegisterSessionRequest,
    SessionOut,
)
from appflow.services.account_settings_service import (
    change_password,
    register_session,
    get_sessions,
    terminate_session,
    log_session_expiry,
)
from appflow.utils import actor_id

account_settings_router = APIRouter(prefix="/account", tags=["Account Settings"])


@account_settings_router.post("/change-password")
def change_password_endpoint(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    result = change_password(
        current_user,
        payload.current_password,
        payload.new_password,
        payload.confirm_password,
        db,
    )
    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])
    return result


@account_settings_router.post("/sessions")
def register_session_endpoint(
    payload: RegisterSessionRequest,
    request: Request,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    ip = payload.ip_address or (request.client.host if request.client else None)
    session = register_session(current_user, ip, payload.device_info, db)
    return {"success": True, "data": SessionOut.model_validate(session)}


@account_settings_router.get("/sessions")
def get_sessions_endpoint(
    request: Request,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    device_info = request.headers.get("user-agent", "")
    sessions = get_sessions(current_user, db, requesting_device_info=device_info)
    return {"sessions": [SessionOut.model_validate(s) for s in sessions]}


@account_settings_router.post("/log-session-expiry")
def log_session_expiry_endpoint(
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    return log_session_expiry(current_user, db)


@account_settings_router.delete("/sessions/{session_id}")
def terminate_session_endpoint(
    session_id: int,
    request: Request,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    device_info = request.headers.get("user-agent", "")
    result = terminate_session(session_id, current_user, db, requesting_device_info=device_info)
    if not result["success"]:
        raise HTTPException(status_code=result["status"], detail=result["message"])
    return result
