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
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from fleet.deps import CalendarEvent, create_notification
from fleet.models.tables import (
    FleetHire,
    FleetVehicleLicensingAuthority,
    FleetVehicleRecord,
    FleetVehicleService,
)

logger = logging.getLogger(__name__)

# First reminder this many days before expiry, then daily.
REMINDER_WINDOW_DAYS = 7

ROAD_TAX_EVENT = "road_fund_licence_expiry"
PLATING_EVENT = "plating_expiry"
MOT_EVENT = "mot_expiry"
SERVICE_DUE_EVENT = "service_due_mileage"

# Warn when an in-use vehicle is within this many miles of its next service.
MILEAGE_REMINDER_THRESHOLD_MILES = 10000


def _vehicle_label(record: FleetVehicleRecord) -> str:
    reg = (record.registration_number or "").strip()
    make_model = " ".join(
        p for p in ((record.make or "").strip(), (record.model or "").strip()) if p
    )
    return reg or make_model or f"Vehicle #{record.id}"


def _vehicle_module(record: FleetVehicleRecord) -> str:
    context = (getattr(record, "context", None) or "skyline").strip() or "skyline"
    return f"vehicles_{context}"


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
    module: str = "vehicles_skyline",
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
            module=module,  # vehicle expiries belong to Vehicle Management
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
        module=_vehicle_module(record),
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
        module=_vehicle_module(record),
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
        category="Vehicles",  # vehicle expiries → Vehicle Management notification feed
        tab="Vehicles",
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


def _to_int_miles(value) -> Optional[int]:
    """Mileage is stored as free text ('54,210', '54210 mi') — pull the digits."""
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def _already_notified_today(db: Session, recipient: int, title: str, today: date) -> bool:
    from libdata.models.tables import Notification
    start = datetime.combine(today, datetime.min.time())
    return (
        db.query(Notification)
        .filter(Notification.recipient_user_id == recipient)
        .filter(Notification.title == title)
        .filter(Notification.created_at >= start)
        .first()
        is not None
    )


def process_mileage_reminders(db: Session, today: Optional[date] = None) -> Dict[str, int]:
    """Service reminder for in-use vehicles within MILEAGE_REMINDER_THRESHOLD_MILES
    of their next service mileage.

    Current mileage is the same derived reading the Vehicle Details screen shows
    (``_attach_mileage`` → the hire's latest odometer); the target is the newest
    service record's ``next_service_due_at``. Fires a Vehicle Management
    notification once a day per vehicle and keeps one matching system calendar
    event in sync (created when it enters the window, removed when it leaves), so
    the calendar doesn't churn on every poll. Safe to call on every poll.
    """
    today = today or date.today()
    from fleet.services.vehicle_record_service import _attach_mileage
    stats = {"mileage": 0, "no_recipient": 0}

    records: List[FleetVehicleRecord] = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.hire_id.isnot(None))  # in use = linked to a hire
        .all()
    )
    for record in records:
        svc = (
            db.query(FleetVehicleService)
            .filter(FleetVehicleService.vehicle_record_id == record.id)
            .filter(FleetVehicleService.is_deleted.isnot(True))
            .filter(FleetVehicleService.next_service_due_at.isnot(None))
            .order_by(FleetVehicleService.position.desc().nullslast(), FleetVehicleService.id.desc())
            .first()
        )
        if not svc:
            continue
        due = _to_int_miles(svc.next_service_due_at)
        if due is None:
            continue
        _attach_mileage(db, record)  # sets record.latest_mileage_obtained / mileage_obtained_on
        current = _to_int_miles(record.latest_mileage_obtained)
        if current is None:
            continue  # no odometer reading yet → nothing to measure against
        remaining = due - current
        label = _vehicle_label(record)
        want_reminder = remaining <= MILEAGE_REMINDER_THRESHOLD_MILES

        # One system calendar event per service record, written only on a state
        # change (enter/leave the window) so the calendar doesn't churn per poll.
        existing_event = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.source == "system")
            .filter(CalendarEvent.source_type == SERVICE_DUE_EVENT)
            .filter(CalendarEvent.source_ref_id == svc.id)
            .first()
        )
        if want_reminder and not existing_event:
            sync_expiry_event(
                db,
                tenant_id=record.tenant_id,
                source_type=SERVICE_DUE_EVENT,
                source_ref_id=svc.id,
                title=f"Service due soon — {label}",
                description=(
                    f"{label} is about {remaining:,} miles from its next service (due at {due:,} mi)."
                    if remaining >= 0
                    else f"{label} is about {abs(remaining):,} miles past its service point (due at {due:,} mi)."
                ),
                expiry=(record.mileage_obtained_on or today),
                registration=record.registration_number,
                module=_vehicle_module(record),
            )
        elif not want_reminder and existing_event:
            sync_expiry_event(
                db, tenant_id=record.tenant_id, source_type=SERVICE_DUE_EVENT,
                source_ref_id=svc.id, title="", description="", expiry=None,
                registration=record.registration_number,
                module=_vehicle_module(record),
            )

        if not want_reminder:
            continue
        recipient = _recipient(record)
        if not recipient:
            stats["no_recipient"] += 1
            continue
        title = f"Service due soon — {label}"
        if _already_notified_today(db, recipient, title, today):
            continue
        create_notification(
            db,
            recipient_user_id=recipient,
            tenant_id=record.tenant_id,
            category="Vehicles",
            tab="Vehicles",
            title=title,
            description=(
                f"{label} has about {remaining:,} miles left until its next service (due at {due:,} mi). Book it in."
                if remaining >= 0
                else f"{label} is about {abs(remaining):,} miles past its next service (due at {due:,} mi). Book it in."
            ),
        )
        db.commit()
        stats["mileage"] += 1

    if stats["mileage"]:
        logger.info("Fleet mileage service reminders for %s: %s", today, stats)
    return stats


def list_due_reminders(db: Session, side: str = "vehicles", today: Optional[date] = None) -> List[Dict]:
    """Read-only view of the currently-due expiry reminders (does not fire or
    send anything). Same due criteria as ``process_fleet_reminders`` — used to
    show the reminders in the UI.

    ``side`` scopes which reminders belong to the caller's screen:
      * ``vehicles`` (default) — vehicle documents: Road Fund / Plate / MOT.
      * ``skyline`` — driver documents: Driving Licence and (taxi drivers) Taxi
        Badge. Vehicle-doc reminders do not belong to the Skyline (hire) list.
    """
    today = today or date.today()
    window_end = today + timedelta(days=REMINDER_WINDOW_DAYS)
    out: List[Dict] = []

    # ── Skyline (hire) screen: driver-document expiries only ──────────────────
    if (side or "").strip().lower() == "skyline":
        hires = db.query(FleetHire).filter(FleetHire.is_deleted.isnot(True)).all()
        for hire in hires:
            who = (hire.driver_name or "").strip() or f"Hire #{hire.id}"
            lic = hire.driving_licence_end
            if lic and lic <= window_end:
                out.append({
                    "kind": "driving_licence",
                    "title": f"Driving licence {_due_phrase(lic, today)} — {who}",
                    "vehicle": who,
                    "expiry_date": lic.isoformat(),
                    "hire_id": hire.id,
                })
            if (hire.hirer_type or "").strip().lower() == "taxi_driver":
                badge = hire.taxi_badge_expiry
                if badge and badge <= window_end:
                    out.append({
                        "kind": "taxi_badge",
                        "title": f"Taxi badge {_due_phrase(badge, today)} — {who}",
                        "vehicle": who,
                        "expiry_date": badge.isoformat(),
                        "hire_id": hire.id,
                    })
        out.sort(key=lambda x: x["expiry_date"])
        return out

    records = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.road_tax_expiry_date.isnot(None))
        .filter(FleetVehicleRecord.road_tax_expiry_date <= window_end)
        .all()
    )
    for record in records:
        expiry = record.road_tax_expiry_date
        label = _vehicle_label(record)
        out.append({
            "kind": "road_tax",
            "title": f"Road tax {_due_phrase(expiry, today)} — {label}",
            "vehicle": label,
            "expiry_date": expiry.isoformat(),
            "hire_id": record.hire_id,
        })

    authorities = (
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
        for kind, expiry, noun in (
            ("plating", authority.plating_expiry_date, "Plate"),
            ("mot", authority.mot_expiry_date, "MOT"),
        ):
            if not expiry or expiry > window_end:
                continue
            out.append({
                "kind": kind,
                "title": f"{noun} {_due_phrase(expiry, today)} — {label}",
                "vehicle": label,
                "expiry_date": expiry.isoformat(),
                "hire_id": record.hire_id,
            })

    # ── Service due (last service + 6-month interval) — same 7-day window ──────
    # Mirrors the Road Fund / Plate / MOT reminders so Servicing shows up in the
    # modal too. Service-due date = latest serviced_on + 182 days.
    latest_service: Dict[int, date] = {}
    for vid, serviced_on in (
        db.query(FleetVehicleService.vehicle_record_id, FleetVehicleService.serviced_on)
        .filter(FleetVehicleService.is_deleted.isnot(True))
        .filter(FleetVehicleService.serviced_on.isnot(None))
        .all()
    ):
        if vid is None or serviced_on is None:
            continue
        if vid not in latest_service or serviced_on > latest_service[vid]:
            latest_service[vid] = serviced_on
    for vid, serviced_on in latest_service.items():
        due = serviced_on + timedelta(days=182)
        if due > window_end:
            continue
        record = records_by_id.get(vid)
        if record is None:
            record = (
                db.query(FleetVehicleRecord)
                .filter(FleetVehicleRecord.id == vid)
                .filter(FleetVehicleRecord.is_deleted.isnot(True))
                .first()
            )
            if not record:
                continue
            records_by_id[vid] = record
        label = _vehicle_label(record)
        out.append({
            "kind": "service",
            "title": f"Service {_due_phrase(due, today)} — {label}",
            "vehicle": label,
            "expiry_date": due.isoformat(),
            "hire_id": record.hire_id,
        })

    out.sort(key=lambda x: x["expiry_date"])
    return out


def list_all_expiries(db: Session, context: Optional[str] = None) -> List[Dict]:
    """Every vehicle expiry (road fund / plate / MOT) with its actual date, for
    the Fleet calendar.

    Unlike ``list_due_reminders`` this is NOT limited to the 7-day due window and
    is read straight from the source tables — so the calendar shows the real
    future dates and covers records that predate the system-event sync. Titles
    are static ("<kind> expiry — <vehicle>"), never time-relative, because they
    sit on a fixed calendar day.
    """
    out: List[Dict] = []

    records_q = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.road_tax_expiry_date.isnot(None))
    )
    if context:
        records_q = records_q.filter(FleetVehicleRecord.context == context)
    records = records_q.all()
    def _make_model(rec) -> str:
        return " ".join(p for p in ((rec.make or "").strip(), (rec.model or "").strip()) if p)

    for record in records:
        label = _vehicle_label(record)
        out.append({
            "kind": "road_tax",
            "title": f"Road Fund expiry — {label}",
            "vehicle": label,
            "make_model": _make_model(record),
            "authority": "DVLA",
            "expiry_date": record.road_tax_expiry_date.isoformat(),
            "hire_id": record.hire_id,
        })

    authorities_q = (
        db.query(FleetVehicleLicensingAuthority)
        .join(FleetVehicleRecord, FleetVehicleRecord.id == FleetVehicleLicensingAuthority.vehicle_record_id)
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
    )
    if context:
        authorities_q = authorities_q.filter(FleetVehicleRecord.context == context)
    authorities = authorities_q.all()
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
        for kind, expiry, noun, auth in (
            ("plating", authority.plating_expiry_date, "Plate", authority.licensing_authority),
            ("mot", authority.mot_expiry_date, "MOT", authority.mot_centre_name),
        ):
            if not expiry:
                continue
            out.append({
                "kind": kind,
                "title": f"{noun} expiry — {label}",
                "vehicle": label,
                "make_model": _make_model(record),
                "authority": (auth or "").strip() or None,
                "expiry_date": expiry.isoformat(),
                "hire_id": record.hire_id,
            })

    out.sort(key=lambda x: x["expiry_date"])
    return out
