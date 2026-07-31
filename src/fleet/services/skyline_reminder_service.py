"""Skyline (hire-side) reminders, surfaced on the Skyline calendar.

Mirrors reminder_watcher (which handles vehicle expiries for Vehicle Management)
but for hire concerns — the weekly Payment Day and PCN reminders / response
deadlines. Each is an upserted *system* CalendarEvent tagged module="skyline",
keyed on (source_type, source_ref_id) so a change replaces the event rather than
stacking a stale one. This is what keeps Skyline's calendar from being empty now
that the vehicle expiries live under Vehicle Management.
"""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from fleet.deps import CalendarEvent, create_notification
from fleet.models.tables import FleetHire, FleetPcn, FleetPcnReminder
from libdata.models.tables import Notification

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# First alert this many days before the due date, then daily until it passes.
REMINDER_WINDOW_DAYS = 7


def _sync_event(
    db: Session,
    *,
    tenant_id: Optional[int],
    source_type: str,
    source_ref_id: int,
    title: str,
    description: str,
    on_date: Optional[date],
    actor: Optional[int] = None,
    recurrence_rule: Optional[str] = None,
) -> None:
    """Upsert (or remove) one system Skyline calendar event."""
    existing = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.source == "system")
        .filter(CalendarEvent.source_type == source_type)
        .filter(CalendarEvent.source_ref_id == source_ref_id)
        .all()
    )
    for ev in existing:
        db.delete(ev)

    if on_date:
        db.add(CalendarEvent(
            tenant_id=tenant_id,
            title=title,
            event_type="Reminder",
            status="Scheduled",
            start_date=on_date,
            end_date=on_date,
            description=description,
            module="skyline",  # hire-side reminders belong to Skyline
            source="system",
            source_type=source_type,
            source_ref_id=source_ref_id,
            recurrence_rule=recurrence_rule,
            created_by=actor,
        ))


def _next_weekday(day_name: Optional[str], today: Optional[date] = None) -> Optional[date]:
    today = today or date.today()
    try:
        target = WEEKDAYS.index((day_name or "").strip().title())
    except ValueError:
        return None
    return today + timedelta(days=(target - today.weekday()) % 7)


def sync_payment_event(db: Session, hire, actor: Optional[int] = None) -> None:
    """A weekly recurring 'payment due' event on the hire's Payment Day.

    Removed once the hire has no Payment Day, or its schedule end date has passed.
    """
    if not hire:
        return
    on = None
    if getattr(hire, "payment_day", None):
        end = getattr(hire, "payment_hire_end_date", None)
        if not end or end >= date.today():
            on = _next_weekday(hire.payment_day)
    ref = getattr(hire, "fleet_reference", None) or f"Hire #{hire.id}"
    amount = (getattr(hire, "weekly_hire_payment", "") or "").strip()
    _sync_event(
        db,
        tenant_id=getattr(hire, "tenant_id", None),
        source_type="payment_due",
        source_ref_id=hire.id,
        title=f"Weekly hire payment due — {ref}",
        description=(
            f"Weekly hire payment{f' of £{amount}' if amount else ''} due on {hire.payment_day}."
        ),
        on_date=on,
        actor=actor,
        recurrence_rule="Weekly",
    )
    db.commit()


def sync_pcn_events(db: Session, pcn: FleetPcn, actor: Optional[int] = None) -> None:
    """The PCN's response deadline + each of its reminders as Skyline events."""
    if not pcn:
        return
    ref = pcn.pcn_number or f"PCN #{pcn.id}"
    council = f" ({pcn.council_name})" if pcn.council_name else ""

    _sync_event(
        db,
        tenant_id=pcn.tenant_id,
        source_type="pcn_response_deadline",
        source_ref_id=pcn.id,
        title=f"PCN response deadline — {ref}",
        description=f"Response deadline for PCN {ref}{council}.",
        on_date=pcn.response_deadline,
        actor=actor,
    )

    for r in db.query(FleetPcnReminder).filter(FleetPcnReminder.pcn_id == pcn.id).all():
        _sync_event(
            db,
            tenant_id=pcn.tenant_id,
            source_type="pcn_reminder",
            source_ref_id=r.id,
            title=f"PCN reminder ({r.reminder_type}) — {ref}",
            description=f"PCN {ref}{council} — {r.reminder_type} reminder.",
            on_date=r.reminder_date,
            actor=actor,
        )
    db.commit()


# --- Bell alerts (Notification rows) --------------------------------------
# Lazy watcher, mirrors reminder_watcher.process_fleet_reminders but for hire
# concerns and tagged category/tab="Fleet" so the Skyline notification bell
# picks them up. Fired on every /notifications poll.

def _due_phrase(due: date, today: date) -> str:
    days = (due - today).days
    if days < 0:
        return f"overdue by {abs(days)} day{'s' if abs(days) != 1 else ''}"
    if days == 0:
        return "due today"
    return f"due in {days} day{'s' if days != 1 else ''}"


def _already_notified(db: Session, recipient: int, title: str) -> bool:
    """One alert per (item, day): the due phrase changes daily, so an existing
    row with this exact title means we've already fired it today."""
    return (
        db.query(Notification)
        .filter(Notification.recipient_user_id == recipient, Notification.title == title)
        .first()
        is not None
    )


def _notify(db: Session, *, recipient: int, tenant_id, title: str, description: str) -> bool:
    if not recipient or _already_notified(db, recipient, title):
        return False
    create_notification(
        db,
        recipient_user_id=recipient,
        tenant_id=tenant_id,
        category="Fleet",
        tab="Fleet",
        title=title,
        description=description,
    )
    return True


def process_skyline_reminders(db: Session, today: Optional[date] = None) -> dict:
    """Fire any due Skyline (hire-side) reminders. Safe to call on every poll."""
    today = today or date.today()
    window_end = today + timedelta(days=REMINDER_WINDOW_DAYS)
    stats = {"payment": 0, "pcn": 0}

    # --- Weekly payment due (Payment Day landing within the window) ---
    hires = (
        db.query(FleetHire)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(FleetHire.payment_day.isnot(None))
        .all()
    )
    for hire in hires:
        end = getattr(hire, "payment_hire_end_date", None)
        if end and end < today:
            continue
        due = _next_weekday(hire.payment_day, today)
        if not due or due > window_end:
            continue
        ref = hire.fleet_reference or f"Hire #{hire.id}"
        amount = (hire.weekly_hire_payment or "").strip()
        if _notify(
            db,
            recipient=hire.updated_by or hire.created_by,
            tenant_id=hire.tenant_id,
            title=f"Weekly hire payment {_due_phrase(due, today)} — {ref}",
            description=f"Weekly hire payment{f' of £{amount}' if amount else ''} for {ref} is {_due_phrase(due, today)}.",
        ):
            stats["payment"] += 1

    # --- PCN response deadlines within the window ---
    pcns = db.query(FleetPcn).all()
    pcn_by_id = {p.id: p for p in pcns}
    for pcn in pcns:
        ref = pcn.pcn_number or f"PCN #{pcn.id}"
        if pcn.response_deadline and today <= pcn.response_deadline <= window_end:
            if _notify(
                db,
                recipient=pcn.updated_by or pcn.created_by,
                tenant_id=pcn.tenant_id,
                title=f"PCN response {_due_phrase(pcn.response_deadline, today)} — {ref}",
                description=f"Response deadline for PCN {ref} is {_due_phrase(pcn.response_deadline, today)}.",
            ):
                stats["pcn"] += 1

    # --- Explicit PCN reminders within the window ---
    reminders = (
        db.query(FleetPcnReminder)
        .filter(FleetPcnReminder.reminder_date.isnot(None))
        .all()
    )
    for r in reminders:
        if not (today <= r.reminder_date <= window_end):
            continue
        pcn = pcn_by_id.get(r.pcn_id)
        if not pcn:
            continue
        ref = pcn.pcn_number or f"PCN #{pcn.id}"
        if _notify(
            db,
            recipient=pcn.updated_by or pcn.created_by,
            tenant_id=pcn.tenant_id,
            title=f"PCN {r.reminder_type} {_due_phrase(r.reminder_date, today)} — {ref}",
            description=f"PCN {ref} — {r.reminder_type} reminder is {_due_phrase(r.reminder_date, today)}.",
        ):
            stats["pcn"] += 1

    return stats
