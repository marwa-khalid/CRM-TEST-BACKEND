from sqlalchemy.orm import Session
from libdata.models.tables import User, UserSession, PasswordHistory
from libauth.token_util import verify_hash, create_hash


def change_password(user_id: int, current_password: str, new_password: str, confirm_password: str, db: Session):
    if new_password != confirm_password:
        return {"success": False, "status": 400, "message": "Passwords do not match"}

    if len(new_password) < 8:
        return {"success": False, "status": 400, "message": "Password must be at least 8 characters"}

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"success": False, "status": 404, "message": "User not found"}

    if not verify_hash(current_password, user.password):
        return {"success": False, "status": 400, "message": "Current password is incorrect"}

    if new_password == current_password:
        return {"success": False, "status": 400, "message": "New password must be different from current password"}

    history = (
        db.query(PasswordHistory)
        .filter(PasswordHistory.user_id == user_id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(5)
        .all()
    )
    for h in history:
        if verify_hash(new_password, h.password_hash):
            return {"success": False, "status": 400, "message": "Cannot reuse a recent password"}

    hashed = create_hash(new_password)
    user.password = hashed
    db.add(PasswordHistory(user_id=user_id, password_hash=hashed))
    db.commit()

    # System alert: password changed (in-app only).
    try:
        from appflow.services.notification_service import safe_notify
        safe_notify(
            db, recipient_user_id=user_id, tenant_id=getattr(user, "tenant_id", None), actor_user_id=user_id,
            category="System Alert", tab="System", title="Password Changed",
            description="Your account password was changed successfully.",
        )
    except Exception:
        pass

    return {"success": True, "status": 200, "message": "Password updated successfully"}


def register_session(user_id: int, ip_address: str, device_info: str, db: Session):
    # Is this a device we've never seen for this user? (before adding the new one)
    is_new_device = device_info and not db.query(UserSession.id).filter(
        UserSession.user_id == user_id,
        UserSession.device_info == device_info,
    ).first()

    # Mark all existing sessions as not current
    db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.is_deleted == False,
    ).update({"is_current": False})

    session = UserSession(
        user_id=user_id,
        ip_address=ip_address,
        device_info=device_info,
        is_current=True,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # System alert: new device sign-in (in-app only).
    if is_new_device:
        try:
            from appflow.services.notification_service import safe_notify
            user = db.query(User).filter(User.id == user_id).first()
            safe_notify(
                db, recipient_user_id=user_id, tenant_id=getattr(user, "tenant_id", None), actor_user_id=user_id,
                category="System Alert", tab="System", title="New Device Sign-In",
                description="A new sign-in to your account was detected. If this wasn't you, change your password.",
            )
        except Exception:
            pass

    return session


def get_sessions(user_id: int, db: Session, requesting_device_info: str = ""):
    sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.is_deleted == False,
            UserSession.is_active == True,
        )
        .order_by(UserSession.created_at.desc())
        .all()
    )
    # Compute is_current relative to the requesting device, not the stale DB flag
    for session in sessions:
        session.is_current = bool(
            requesting_device_info and session.device_info == requesting_device_info
        )
    # Sort: current device first, then by most recent
    sessions.sort(key=lambda s: (not s.is_current, -(s.created_at.timestamp() if s.created_at else 0)))
    return sessions


def log_session_expiry(user_id: int, db: Session):
    db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.is_current == True,
        UserSession.is_deleted == False,
    ).update({"is_current": False, "is_active": False})
    db.commit()
    return {"success": True, "message": "Session expiry logged"}


def terminate_session(session_id: int, user_id: int, db: Session, requesting_device_info: str = ""):
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == user_id,
        UserSession.is_deleted == False,
    ).first()
    if not session:
        return {"success": False, "status": 404, "message": "Session not found"}
    # Block terminating the requesting device's own session
    if requesting_device_info and session.device_info == requesting_device_info:
        return {"success": False, "status": 400, "message": "Cannot terminate your current session"}
    session.is_deleted = True
    session.is_active = False
    db.commit()
    return {"success": True, "status": 200, "message": "Session terminated"}
