import os
import re
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy.orm import Session

from libdata.models.tables import Notification, User
from appflow.logger import logger


# ── optional email notifications (story #7) ──────────────────────────────────
def _emails_enabled() -> bool:
    return os.getenv("NOTIFICATION_EMAILS", "true").strip().lower() in ("1", "true", "yes", "on")


def _sg_key() -> Optional[str]:
    # Prefer the env var (so rotating the key fixes both this and invites);
    # fall back to the existing constant so it keeps working before that's set.
    key = os.getenv("SENDGRID_API_KEY")
    if key:
        return key
    try:
        from appflow.services.invite_service import SENDGRID_API_KEY as _k
        return _k
    except Exception:
        return None


def _email_html(title: str, description: str) -> str:
    font = "'Stack Sans Headline', Helvetica, Arial, sans-serif"
    return f"""
    <div style="font-family: {font}; background:#ffffff; padding:32px;">
      <table align="center" width="600" cellpadding="0" cellspacing="0"
        style="font-family: {font}; background:#ffffff;">
        <tr><td style="padding:32px;">
          <p style="color:#0352FD; font-size:12px; font-weight:600; font-family:{font}; letter-spacing:.04em; margin:0 0 8px;">NATIONWIDE ASSIST CRM</p>
          <h2 style="color:#000000; font-size:20px; font-weight:600; font-family:{font}; line-height:1.0; margin:0 0 12px;">{title}</h2>
          <p style="color:#444444; font-size:14px; font-weight:400; font-family:{font}; line-height:1.57; margin:0;">{description}</p>
          <p style="color:#888888; font-size:12px; font-weight:400; font-family:{font}; margin:24px 0 0;">Log in to the CRM to view and respond.</p>
        </td></tr>
      </table>
    </div>
    """


def send_notification_email(to_email: str, subject: str, description: str) -> None:
    """Best-effort email for an important notification. Never raises."""
    if not _emails_enabled():
        return
    if not to_email or "@" not in to_email:
        return
    try:
        # Graph-first so it reaches Outlook; SendGrid fallback.
        from appflow.services.email_delivery import send_email as deliver_email
        deliver_email(
            to=to_email,
            subject=subject,
            html=_email_html(subject, description),
        )
    except Exception as e:
        logger.warning(f"notification email failed: {e}")


def create_notification(
    db: Session,
    *,
    recipient_user_id: int,
    tenant_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    category: str = "System",
    tab: str = "System",
    title: str = "",
    description: str = "",
    claim_id: Optional[int] = None,
    email: bool = False,
) -> Notification:
    n = Notification(
        recipient_user_id=recipient_user_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        category=category,
        tab=tab,
        title=title,
        description=description,
        claim_id=claim_id,
        is_read=False,
    )
    db.add(n)
    db.commit()
    db.refresh(n)

    # Optional email for important notifications (story #7).
    if email:
        recipient = db.query(User).filter(User.id == recipient_user_id).first()
        send_notification_email(getattr(recipient, "user_name", None), title, description)
    return n


def _display_name(user_name: str) -> str:
    un = user_name or ""
    return un.split("@")[0] if "@" in un else un


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


ASSIGNEE_EMAIL_ALIASES = {
    # Demo mapping: the task dropdown label is "Hina Sadaf", but the demo
    # account email is hinasada@yopmail.com.
    "hinasadaf": "hinasada@yopmail.com",
}


def safe_notify(db: Session, **kwargs) -> None:
    """Create a notification without ever breaking the caller's transaction."""
    try:
        create_notification(db, **kwargs)
    except Exception:
        db.rollback()


def resolve_user_by_name(db: Session, name, tenant_id: Optional[int] = None) -> Optional[int]:
    """Map a task assignee label, display name, or email to a user id."""
    if not name:
        return None
    target = str(name).strip().lower()
    target_key = _name_key(target)
    target_values = {target}
    alias_email = ASSIGNEE_EMAIL_ALIASES.get(target_key)
    if alias_email:
        target_values.add(alias_email.lower())
    q = db.query(User).filter(User.is_deleted == False)
    if tenant_id is not None:
        q = q.filter(User.tenant_id == tenant_id)
    for u in q.all():
        un = (u.user_name or "")
        disp = un.split("@")[0] if "@" in un else un
        full_name = " ".join(
            p for p in [getattr(u, "first_name", None), getattr(u, "last_name", None)] if p
        )
        candidates = [un, disp, full_name]
        if any(c and (c.lower() in target_values or _name_key(c) == target_key) for c in candidates):
            return u.id
    if alias_email:
        user = (
            db.query(User)
            .filter(User.is_deleted == False, User.user_name == alias_email)
            .first()
        )
        if user:
            return user.id
    return None


def create_mention_notifications(
    db: Session,
    *,
    note_text: str,
    claim_id: Optional[int],
    actor_user_id: Optional[int],
    tenant_id: Optional[int],
    case_reference: str = "",
) -> int:
    """Parse @mentions from a note and notify each tagged user. Returns count."""
    handles = set(re.findall(r"@([A-Za-z0-9._\-]+)", note_text or ""))
    if not handles:
        return 0

    actor_name = ""
    if actor_user_id:
        actor = db.query(User).filter(User.id == actor_user_id).first()
        actor_name = _display_name(actor.user_name) if actor else ""

    users = db.query(User).filter(User.is_deleted == False)
    if tenant_id is not None:
        users = users.filter(User.tenant_id == tenant_id)

    count = 0
    ref = f" in Claim #{case_reference}" if case_reference else " in this claim"
    for u in users.all():
        if _display_name(u.user_name) in handles:
            create_notification(
                db,
                recipient_user_id=u.id,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                category="Mention",
                tab="Mentions",
                title="You were mentioned",
                description=f"{actor_name or 'Someone'} tagged you{ref}.",
                claim_id=claim_id,
                email=True,
            )
            count += 1
    return count


def _time_ago(dt) -> str:
    if not dt:
        return ""
    now = datetime.now(dt.tzinfo) if getattr(dt, "tzinfo", None) else datetime.utcnow()
    diff = (now - dt).total_seconds()
    if diff < 60:
        return "Just now"
    m = int(diff // 60)
    if m < 60:
        return f"{m}m ago"
    h = int(m // 60)
    if h < 24:
        return f"{h}h ago"
    d = int(h // 24)
    return "1d ago" if d == 1 else f"{d}d ago"


def _group(dt) -> str:
    if not dt:
        return "Earlier"
    now = datetime.now(dt.tzinfo) if getattr(dt, "tzinfo", None) else datetime.utcnow()
    if dt.date() == now.date():
        return "Today"
    if dt.date() == (now - timedelta(days=1)).date():
        return "Yesterday"
    return "Earlier"


def _to_out(n: Notification) -> dict:
    return {
        "id": f"db-{n.id}",
        "notif_id": n.id,
        "tab": n.tab or "System",
        "category": n.category or "System",
        "title": n.title or "",
        "description": n.description or "",
        "time": _time_ago(n.created_at),
        "group": _group(n.created_at),
        "ts": int(n.created_at.timestamp() * 1000) if n.created_at else None,
        "unread": not bool(n.is_read),
        "claim_id": n.claim_id,
    }


def list_for_user(db: Session, user_id: int, limit: int = 100) -> List[dict]:
    rows = (
        db.query(Notification)
        .filter(Notification.recipient_user_id == user_id, Notification.is_deleted == False)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )
    return [_to_out(n) for n in rows]
