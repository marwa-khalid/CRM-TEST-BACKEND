"""Road Fund Licence: expiry calculation, calendar event, and reminders.

Renewing road tax sets a new expiry a year out. That expiry drives a
system-generated calendar event and a daily reminder in the last seven days.
Renewing again replaces both, so a vehicle only ever has one live schedule.
"""
import logging
from datetime import date
from typing import Dict, Optional

from sqlalchemy.orm import Session

from fleet.deps import CalendarEvent, create_notification
from fleet.models.tables import FleetVehicleRecord

logger = logging.getLogger(__name__)

# The first reminder goes out this many days before expiry, then daily.
REMINDER_WINDOW_DAYS = 7
EVENT_SOURCE_TYPE = "road_fund_licence_expiry"


def add_one_year(value: date) -> date:
    """Road tax runs 12 months. 29 Feb renews to 28 Feb — replace() would raise."""
    try:
        return value.replace(year=value.year + 1)
    except ValueError:
        return value.replace(year=value.year + 1, day=28)


def _vehicle_label(record: FleetVehicleRecord) -> str:
    reg = (record.registration_number or "").strip()
    make_model = " ".join(p for p in ((record.make or "").strip(), (record.model or "").strip()) if p)
    return reg or make_model or f"Vehicle #{record.id}"


def _delete_existing_event(db: Session, record_id: int) -> int:
    """Remove any previous road-tax event for this vehicle.

    Renewal replaces the schedule rather than adding to it, so stale events can
    never accumulate and alert on a date that no longer applies.
    """
    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.source == "system")
        .filter(CalendarEvent.source_type == EVENT_SOURCE_TYPE)
        .filter(CalendarEvent.source_ref_id == record_id)
        .all()
    )
    for event in events:
        db.delete(event)
    return len(events)


def sync_expiry_and_event(
    db: Session, record: FleetVehicleRecord, actor: Optional[int] = None,
) -> FleetVehicleRecord:
    """Recalculate expiry from the renewal date and rebuild the calendar event."""
    renewed = record.road_tax_renewed_on
    _delete_existing_event(db, record.id)

    if not renewed:
        record.road_tax_expiry_date = None
        record.road_tax_reminder_sent_on = None
        db.commit()
        db.refresh(record)
        return record

    expiry = add_one_year(renewed)
    record.road_tax_expiry_date = expiry
    # A new expiry means the old reminder schedule no longer applies.
    record.road_tax_reminder_sent_on = None

    label = _vehicle_label(record)
    db.add(CalendarEvent(
        tenant_id=record.tenant_id,
        title=f"Road Fund Licence expires — {label}",
        event_type="Reminder",
        status="Scheduled",
        start_date=expiry,
        end_date=expiry,
        description=(
            f"Road tax for {label} expires on {expiry.strftime('%d/%m/%Y')}. "
            f"Last renewed on {renewed.strftime('%d/%m/%Y')}."
        ),
        vehicle_registration=(record.registration_number or None),
        source="system",
        source_type=EVENT_SOURCE_TYPE,
        source_ref_id=record.id,
        created_by=actor,
    ))
    db.commit()
    db.refresh(record)
    return record


def run_road_tax_reminders(db: Session, today: Optional[date] = None) -> Dict[str, int]:
    """Kept as the cron entry point; the watcher is the single implementation."""
    from fleet.services.reminder_watcher import process_fleet_reminders
    return process_fleet_reminders(db, today)
