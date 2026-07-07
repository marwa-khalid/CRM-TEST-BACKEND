from typing import Optional, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from libdata.models.tables import Task, TaskNote, TaskHistory, User


def _name(db: Session, user_id: Optional[int]) -> str:
    if not user_id:
        return "User"
    u = db.query(User).filter(User.id == user_id).first()
    un = (u.user_name if u else "") or ""
    return un.split("@")[0] if "@" in un else (un or "User")


def log_history(db: Session, task_id: int, actor: Optional[int], event_type: str,
                title: str, detail: str = "", tenant_id: Optional[int] = None) -> None:
    """Append a task-history event. Never breaks the caller."""
    try:
        db.add(TaskHistory(
            task_id=task_id, actor_user_id=actor, event_type=event_type,
            title=title, detail=detail, tenant_id=tenant_id,
        ))
        db.commit()
    except Exception:
        db.rollback()


def _note_out(db: Session, n: TaskNote) -> dict:
    return {
        "id": n.id,
        "text": n.text or "",
        "author_id": n.author_user_id,
        "author_name": _name(db, n.author_user_id),
        "created_at": n.created_at,
    }


def list_notes(db: Session, task_id: int) -> List[dict]:
    rows = (
        db.query(TaskNote)
        .filter(TaskNote.task_id == task_id, TaskNote.is_deleted == False)
        .order_by(TaskNote.created_at.desc(), TaskNote.id.desc())
        .all()
    )
    return [_note_out(db, n) for n in rows]


def add_note(db: Session, task_id: int, text: str, author: Optional[int], tenant_id: Optional[int]) -> dict:
    task = db.query(Task).filter(Task.id == task_id, Task.is_deleted == False).first()
    if not task:
        raise HTTPException(404, "Task not found")
    note = TaskNote(task_id=task_id, author_user_id=author, text=text, tenant_id=tenant_id)
    db.add(note)
    db.commit()
    db.refresh(note)

    # @-mentions -> notify the tagged real users (same as case activity).
    try:
        from appflow.services.notification_service import create_mention_notifications
        create_mention_notifications(
            db, note_text=text, claim_id=task.claim_id, actor_user_id=author,
            tenant_id=tenant_id, case_reference=task.claim_reference or "",
        )
    except Exception:
        db.rollback()

    log_history(db, task_id, author, "note", "Note added", (text or "")[:120], tenant_id)
    return _note_out(db, note)


def delete_note(db: Session, note_id: int, user_id: Optional[int]) -> dict:
    note = db.query(TaskNote).filter(TaskNote.id == note_id, TaskNote.is_deleted == False).first()
    if not note:
        raise HTTPException(404, "Note not found")
    note.is_deleted = True
    db.commit()
    return {"detail": "Note deleted"}


def _history_out(db: Session, h: TaskHistory) -> dict:
    return {
        "id": h.id,
        "event_type": h.event_type,
        "title": h.title or "",
        "detail": h.detail or "",
        "actor_name": _name(db, h.actor_user_id),
        "created_at": h.created_at,
    }


def list_history(db: Session, task_id: int) -> List[dict]:
    rows = (
        db.query(TaskHistory)
        .filter(TaskHistory.task_id == task_id, TaskHistory.is_deleted == False)
        .order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())
        .all()
    )
    return [_history_out(db, h) for h in rows]
