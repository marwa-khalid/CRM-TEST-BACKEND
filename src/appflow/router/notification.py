from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from libdata.settings import get_session
from libdata.models.tables import Notification
from appflow.utils import actor_id
from appflow.services.notification_service import list_for_user

notification_router = APIRouter(prefix="/notifications", tags=["Notifications"])


@notification_router.get("")
def list_notifications(db: Session = Depends(get_session), current_user=Depends(actor_id)):
    # Lazily fire any due calendar reminders so they surface without a scheduler.
    try:
        from appflow.services.calendar_event_service import CalendarEventService
        CalendarEventService.process_due_reminders(db)
    except Exception:
        db.rollback()
    # Fleet expiry reminders (road tax / plate / MOT) use the same lazy design.
    try:
        from fleet.services.reminder_watcher import process_fleet_reminders
        process_fleet_reminders(db)
    except Exception:
        db.rollback()
    return list_for_user(db, current_user)


@notification_router.post("/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_session), current_user=Depends(actor_id)):
    n = (
        db.query(Notification)
        .filter(Notification.id == notif_id, Notification.recipient_user_id == current_user)
        .first()
    )
    if not n:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return {"success": True}


@notification_router.post("/read-all")
def mark_all_read(db: Session = Depends(get_session), current_user=Depends(actor_id)):
    db.query(Notification).filter(
        Notification.recipient_user_id == current_user,
        Notification.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"success": True}


@notification_router.post("/unread-all")
def mark_all_unread(db: Session = Depends(get_session), current_user=Depends(actor_id)):
    db.query(Notification).filter(
        Notification.recipient_user_id == current_user,
        Notification.is_read == True,
    ).update({"is_read": False})
    db.commit()
    return {"success": True}
