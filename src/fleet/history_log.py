"""Post fleet-hire actions to the shared Case History as records, scoped to the
hire (scope_type = fleet_hire, scope_id = hire_id). Best-effort — a logging
failure never breaks the underlying fleet action."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session


def _log(
    db: Session,
    hire_id: int,
    *,
    action_type,
    details: str,
    subject: Optional[str] = None,
    actor: Optional[int] = None,
    correspondent: Optional[str] = None,
    documents=None,
    source: str = "note",
) -> None:
    from appflow.services.case_history_service import CaseHistoryService
    CaseHistoryService.log_document_record(
        db,
        hire_id,
        action_type=action_type,
        details=details,
        subject=subject,
        correspondent=correspondent,
        documents=documents,
        source=source,
        current_user=actor,
        scope_type="fleet_hire",
        scope_id=hire_id,
    )


# ── PCN reminders / deadlines → Diary (DY) ────────────────────────────────────
_PCN_REMINDER_LABELS = {
    "council_response_deadline": "Council response deadline",
    "appeal_deadline": "Appeal deadline",
    "payment_due_date": "Payment due date",
    "follow_up_reminder": "Follow-up reminder",
}


def log_pcn_reminder(
    db: Session,
    hire_id: int,
    *,
    reminder_type: str,
    reminder_date: Optional[date],
    reminder_time: Optional[str] = None,
    actor: Optional[int] = None,
) -> None:
    """Log a PCN reminder / deadline as a Diary (DY) entry when its date is set, so
    the calendar deadline also surfaces in the hire's History."""
    if not reminder_date:
        return
    try:
        from libdata.enums import CaseHistoryActionType
        label = _PCN_REMINDER_LABELS.get((reminder_type or "").strip().lower(), "PCN reminder")
        when = reminder_date.strftime("%d/%m/%Y") if hasattr(reminder_date, "strftime") else str(reminder_date)
        t = (reminder_time or "").strip()
        details = f"{label}: {when} {t}".strip()
        _log(
            db,
            hire_id,
            action_type=CaseHistoryActionType.DIARY,
            details=details,
            subject=label,
            actor=actor,
            source="diary",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[Fleet history] PCN reminder log failed: {exc}")


# ── On / Off-hire vehicle movement (MO) ───────────────────────────────────────
def log_hire_movement(
    db: Session,
    hire_id: int,
    *,
    registration: Optional[str],
    on_hire: bool,
    actor: Optional[int] = None,
) -> None:
    """Auto-log an on/off-hire vehicle movement as a Movement (MO) record on the
    hire's History — the "MO" rows in the legacy Skyline system. Fired when a
    vehicle's hire_status transitions to on_hire (placed on hire) or off_hire."""
    try:
        from libdata.enums import CaseHistoryActionType
        reg = (registration or "").strip().upper() or "Vehicle"
        details = f"{reg} placed on hire" if on_hire else f"{reg} off-hired"
        _log(
            db,
            hire_id,
            action_type=CaseHistoryActionType.MOVEMENT,
            details=details,
            subject="On Hire" if on_hire else "Off Hire",
            actor=actor,
            source="movement",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[Fleet history] movement log failed: {exc}")


# ── WhatsApp / SMS to driver (SE) ─────────────────────────────────────────────
def log_hire_message(
    db: Session,
    hire_id: int,
    *,
    to_number: str,
    body: str,
    kind: str = "",
    actor: Optional[int] = None,
) -> None:
    """Log an outbound WhatsApp/SMS to the driver as a Send Email (SE) record on the
    hire's History (outbound driver correspondence)."""
    try:
        from libdata.enums import CaseHistoryActionType
        text = (body or "").strip() or (f"WhatsApp template: {kind}" if kind else "WhatsApp message")
        _log(
            db,
            hire_id,
            action_type=CaseHistoryActionType.SEND_EMAIL,
            details=text,
            subject="WhatsApp to driver",
            actor=actor,
            correspondent=(to_number or "").strip() or None,
            source="whatsapp",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[Fleet history] WhatsApp log failed: {exc}")
