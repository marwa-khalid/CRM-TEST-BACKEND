"""Fleet expiry reminders — a lazy watcher, not a scheduler.

Mirrors the Claims design (``CalendarEventService.process_due_reminders``):
reminders are evaluated whenever notifications are fetched, so nothing depends
on a cron job being configured. The cron entry points in ``fleet/jobs`` remain
as a belt-and-braces path and call straight into here.

Covered expiries, all on the Customer Side of a hire file:

* Road Fund Licence  — fleet_vehicle_record.road_tax_expiry_date
* Plate expiry       — fleet_vehicle_licensing_authority.plating_expiry_date
* MOT expiry         — fleet_vehicle_licensing_authority.mot_expiry_date

Each fires once a day inside its window; a date-stamp column per expiry keeps
that idempotent, so the watcher is safe to call on every notifications poll.
"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from fleet.deps import CalendarEvent, create_notification
from fleet.models.tables import FleetVehicleLicensingAuthority, FleetVehicleRecord

logger = logging.getLogger(__name__)

# First reminder this many days before expiry, then daily.
REMINDER_WINDOW_DAYS = 7

ROAD_TAX_EVENT = "road_fund_licence_expiry"
PLATING_EVENT = "plating_expiry"
MOT_EVENT = "mot_expiry"


def _vehicle_label(record: FleetVehicleRecord) -> str:
    reg = (record.registration_number or "").strip()
    make_model = " ".join(
        p for p in ((record.make or "").strip(), (record.model or "").strip()) if p
    )
    return reg or make_model or f"Vehicle #{record.id}"


def _due_phrase(expiry: date, today: date) -> str:
    days = (expiry - today).days
    if days < 0:
        return f"expired {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
    if days == 0:
        return "expires today"
    return f"expires in {days} day{'s' if days != 1 else ''}"


def _recipient(record: FleetVehicleRecord) -> Optional[int]:
    return record.updated_by or record.created_by


def sync_expiry_event(
    db: Session,
    *,
    tenant_id: Optional[int],
    source_type: str,
    source_ref_id: int,
    title: str,
    description: str,
    expiry: Optional[date],
    registration: Optional[str] = None,
    actor: Optional[int] = None,
) -> None:
    """Upsert (or remove) the system calendar event for one expiry.

    Keyed on (source_type, source_ref_id) so a renewal replaces the event rather
    than stacking a second one alerting on a date that no longer applies.
    """
    existing = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.source == "system")
        .filter(CalendarEvent.source_type == source_type)
        .filter(CalendarEvent.source_ref_id == source_ref_id)
        .all()
    )
    for event in existing:
        db.delete(event)

    if expiry:
        db.add(CalendarEvent(
            tenant_id=tenant_id,
            title=title,
            event_type="Reminder",
            status="Scheduled",
            start_date=expiry,
            end_date=expiry,
            description=description,
            vehicle_registration=(registration or None),
            source="system",
            source_type=source_type,
            source_ref_id=source_ref_id,
            created_by=actor,
        ))
    db.commit()


def sync_authority_events(
    db: Session, authority: FleetVehicleLicensingAuthority, actor: Optional[int] = None,
) -> None:
    """Rebuild the plate and MOT expiry events for one licensing authority."""
    record = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.id == authority.vehicle_record_id)
        .first()
    )
    if not record:
        return
    label = _vehicle_label(record)

    sync_expiry_event(
        db,
        tenant_id=record.tenant_id,
        source_type=PLATING_EVENT,
        source_ref_id=authority.id,
        title=f"Plate expires — {label}",
        description=(
            f"The licence plate for {label} "
            f"({authority.licensing_authority or 'licensing authority'}) expires on "
            f"{authority.plating_expiry_date.strftime('%d/%m/%Y')}."
            if authority.plating_expiry_date else ""
        ),
        expiry=authority.plating_expiry_date,
        registration=record.registration_number,
        actor=actor,
    )
    sync_expiry_event(
        db,
        tenant_id=record.tenant_id,
        source_type=MOT_EVENT,
        source_ref_id=authority.id,
        title=f"MOT expires — {label}",
        description=(
            f"The MOT for {label} expires on "
            f"{authority.mot_expiry_date.strftime('%d/%m/%Y')}."
            if authority.mot_expiry_date else ""
        ),
        expiry=authority.mot_expiry_date,
        registration=record.registration_number,
        actor=actor,
    )


def _fire(
    db: Session,
    record: FleetVehicleRecord,
    *,
    title: str,
    description: str,
) -> bool:
    recipient = _recipient(record)
    if not recipient:
        return False
    create_notification(
        db,
        recipient_user_id=recipient,
        tenant_id=record.tenant_id,
        category="Fleet",
        tab="Fleet",
        title=title,
        description=description,
    )
    return True


def process_fleet_reminders(db: Session, today: Optional[date] = None) -> Dict[str, int]:
    """Fire any due Fleet expiry reminders. Safe to call on every poll."""
    today = today or date.today()
    window_end = today + timedelta(days=REMINDER_WINDOW_DAYS)
    stats = {"road_tax": 0, "plating": 0, "mot": 0, "no_recipient": 0}

    # --- Road Fund Licence: 7 days before expiry, up to the expiry date. The
    # licence simply lapses after that, so nagging past it adds nothing. ---
    records: List[FleetVehicleRecord] = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.road_tax_expiry_date.isnot(None))
        .filter(FleetVehicleRecord.road_tax_expiry_date <= window_end)
        .filter(FleetVehicleRecord.road_tax_expiry_date >= today)
        .all()
    )
    for record in records:
        if record.road_tax_reminder_sent_on == today:
            continue
        expiry = record.road_tax_expiry_date
        label = _vehicle_label(record)
        sent = _fire(
            db, record,
            title=f"Road tax {_due_phrase(expiry, today)} — {label}",
            description=(
                f"The Road Fund Licence for {label} expires on "
                f"{expiry.strftime('%d/%m/%Y')}. Renew it and update the record."
            ),
        )
        if not sent:
            stats["no_recipient"] += 1
            continue
        record.road_tax_reminder_sent_on = today
        db.commit()
        stats["road_tax"] += 1

    # --- Plate and MOT: from 7 days before expiry and CONTINUING once overdue.
    # The user story requires reminders to keep coming until a new certificate is
    # uploaded — which moves the expiry date and ends the schedule by itself. ---
    authorities: List[FleetVehicleLicensingAuthority] = (
        db.query(FleetVehicleLicensingAuthority)
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
        .all()
    )
    records_by_id: Dict[int, FleetVehicleRecord] = {}

    for authority in authorities:
        record = records_by_id.get(authority.vehicle_record_id)
        if record is None:
            record = (
                db.query(FleetVehicleRecord)
                .filter(FleetVehicleRecord.id == authority.vehicle_record_id)
                .filter(FleetVehicleRecord.is_deleted.isnot(True))
                .first()
            )
            if not record:
                continue
            records_by_id[authority.vehicle_record_id] = record
        label = _vehicle_label(record)

        for kind, expiry, stamp_field, noun in (
            ("plating", authority.plating_expiry_date, "plating_reminder_sent_on", "Plate"),
            ("mot", authority.mot_expiry_date, "mot_reminder_sent_on", "MOT"),
        ):
            if not expiry or expiry > window_end:
                continue
            if getattr(authority, stamp_field) == today:
                continue
            sent = _fire(
                db, record,
                title=f"{noun} {_due_phrase(expiry, today)} — {label}",
                description=(
                    f"The {noun.lower()} for {label} expires on {expiry.strftime('%d/%m/%Y')}. "
                    f"Upload the new certificate on the Licensing Authority screen."
                ),
            )
            if not sent:
                stats["no_recipient"] += 1
                continue
            setattr(authority, stamp_field, today)
            db.commit()
            stats[kind] += 1

    if any(v for k, v in stats.items() if k != "no_recipient"):
        logger.info("Fleet expiry reminders for %s: %s", today, stats)
    return stats
