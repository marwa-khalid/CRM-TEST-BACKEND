"""Fleet dashboard aggregations.

Self-contained inside the Fleet slice: nothing here imports the Claims (appflow)
dashboard service, so Fleet stays independently extractable. Only fleet.models
(tables) and the session/tenant passed in are used.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from fleet.models.tables import (
    FleetHire,
    FleetHirePayment,
    FleetHireVehicle,
    FleetVehicleLicensingAuthority,
    FleetVehicleRecord,
    FleetVehicleRegister,
    FleetVehicleService,
)

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _add_months(d: date, months: int) -> date:
    """First-of-month `months` away from `d` (all callers pass day-1 dates)."""
    idx = d.month - 1 + months
    return date(d.year + idx // 12, idx % 12 + 1, 1)


def _month_label(d: date, show_year: bool = False) -> str:
    label = _MONTHS[d.month - 1]
    return f"{label} {d.year}" if show_year else label


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _count_between(dates: List[date], start: date, end: date) -> int:
    """How many hire start-dates fall in the half-open range [start, end)."""
    return sum(1 for d in dates if d and start <= d < end)


def _hire_start_dates(db: Session, tenant_id: Optional[int], status: Optional[str] = None) -> List[date]:
    """Every fleet vehicle-hire start date for the tenant (one row per hired
    vehicle). Soft-deleted hire files and null start dates are excluded.
    `status` (on_hire | off_hire) optionally filters by the vehicle-hire status."""
    query = (
        db.query(FleetHireVehicle.hire_start_date)
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(FleetHireVehicle.hire_start_date.isnot(None))
    )
    if tenant_id is not None:
        query = query.filter(FleetHire.tenant_id == tenant_id)
    if status:
        query = query.filter(func.lower(func.coalesce(FleetHireVehicle.hire_status, "")) == status.strip().lower())
    return [row[0] for row in query.all()]


def _to_float(value) -> float:
    """Parse a money-ish string ('£38,420', '575.00') to a float; 0.0 on junk."""
    if value is None:
        return 0.0
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".", "-.") else 0.0
    except ValueError:
        return 0.0


def _shift_period(d: date, period: str) -> date:
    """`d` moved back exactly one period (a week / month / year), clamping the
    day so e.g. 31 Mar → 28/29 Feb never overflows."""
    if period == "TDY":
        return d - timedelta(days=1)
    if period == "WTD":
        return d - timedelta(weeks=1)
    if period == "YTD":
        try:
            return d.replace(year=d.year - 1)
        except ValueError:  # 29 Feb → 28 Feb
            return d.replace(year=d.year - 1, day=28)
    idx = d.month - 2  # one month back, zero-based
    year, month = d.year + idx // 12, idx % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def _normalise_context(value: Optional[str]) -> Optional[str]:
    ctx = (value or "").strip().lower().replace("-", "_")
    if ctx.startswith("vehicles_"):
        ctx = ctx.split("_", 1)[1]
    return ctx or None


def _vehicle_record_regs_for_context(db: Session, tenant_id: Optional[int], context: Optional[str]) -> Optional[set]:
    ctx = _normalise_context(context)
    if not ctx:
        return None
    q = (
        db.query(FleetVehicleRecord.registration_number)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(func.lower(func.trim(func.coalesce(FleetVehicleRecord.context, ""))) == ctx)
    )
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    return {_norm_reg(row[0]) for row in q.all() if _norm_reg(row[0])}


def _count_hire_vehicle_rows(q, allowed_regs: Optional[set]) -> int:
    if allowed_regs is None:
        return q.with_entities(func.count(FleetHireVehicle.id)).scalar() or 0
    return sum(1 for (reg,) in q.with_entities(FleetHireVehicle.registration_number).all() if _norm_reg(reg) in allowed_regs)


def _on_hire_as_of(db: Session, tenant_id: Optional[int], as_of: date, context: Optional[str] = None) -> int:
    """Vehicles under an active hire on `as_of` (started on/before, not yet ended)."""
    q = (
        db.query(FleetHireVehicle)
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(FleetHireVehicle.hire_start_date.isnot(None))
        .filter(FleetHireVehicle.hire_start_date <= as_of)
        .filter(or_(FleetHireVehicle.hire_end_date.is_(None), FleetHireVehicle.hire_end_date >= as_of))
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    return _count_hire_vehicle_rows(q, _vehicle_record_regs_for_context(db, tenant_id, context))


def _on_hire_started_on(db: Session, tenant_id: Optional[int], day: date, context: Optional[str] = None) -> int:
    """Vehicles that were put on hire on exactly `day`.

    This is an event count, not a current-status count: if the vehicle was also
    off-hired later the same day, it still "went on hire today".
    """
    q = (
        db.query(FleetHireVehicle)
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(FleetHireVehicle.hire_start_date == day)
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    return _count_hire_vehicle_rows(q, _vehicle_record_regs_for_context(db, tenant_id, context))


def _ctx(q, context: Optional[str]):
    """Scope a FleetVehicleRecord query to one VM side (cams / skyline) when given."""
    ctx = _normalise_context(context)
    return q.filter(func.lower(func.trim(func.coalesce(FleetVehicleRecord.context, ""))) == ctx) if ctx else q


def _fleet_total(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> int:
    q = db.query(func.count(FleetVehicleRecord.id)).filter(FleetVehicleRecord.is_deleted.isnot(True))
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    return (_ctx(q, context)).scalar() or 0


def _available_count(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> int:
    """Vehicles genuinely available — status 'Available' in the effective list (which
    already sends on-hire vehicles to On Hire), so it matches the donut's Available."""
    return sum(1 for v in _effective_vehicle_list(db, tenant_id, context) if v["status"] == "Available")


def _income_between(db: Session, tenant_id: Optional[int], start: date, end: date) -> float:
    """Sum of received/partial hire payments with a payment_date in [start, end)."""
    q = (
        db.query(FleetHirePayment.paid_amount)
        .join(FleetHire, FleetHirePayment.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(FleetHirePayment.status.in_(["received", "partial"]))
        .filter(FleetHirePayment.payment_date.isnot(None))
        .filter(FleetHirePayment.payment_date >= start)
        .filter(FleetHirePayment.payment_date < end)
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    return sum(_to_float(row[0]) for row in q.all())


def _overdue_expiries_as_of(db: Session, tenant_id: Optional[int], as_of: date, context: Optional[str] = None) -> int:
    """Road-tax / plate / MOT expiries already lapsed on `as_of`."""
    rt = db.query(func.count(FleetVehicleRecord.id)).filter(
        FleetVehicleRecord.is_deleted.isnot(True),
        FleetVehicleRecord.road_tax_expiry_date.isnot(None),
        FleetVehicleRecord.road_tax_expiry_date < as_of,
    )
    if tenant_id is not None:
        rt = rt.filter(FleetVehicleRecord.tenant_id == tenant_id)
    rt = _ctx(rt, context)

    authority = (
        db.query(FleetVehicleLicensingAuthority)
        .join(FleetVehicleRecord, FleetVehicleLicensingAuthority.vehicle_record_id == FleetVehicleRecord.id)
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        authority = authority.filter(FleetVehicleRecord.tenant_id == tenant_id)
    authority = _ctx(authority, context)
    plate = authority.filter(
        FleetVehicleLicensingAuthority.plating_expiry_date.isnot(None),
        FleetVehicleLicensingAuthority.plating_expiry_date < as_of,
    ).count()
    mot = authority.filter(
        FleetVehicleLicensingAuthority.mot_expiry_date.isnot(None),
        FleetVehicleLicensingAuthority.mot_expiry_date < as_of,
    ).count()
    return (rt.scalar() or 0) + plate + mot


def _overdue_service_as_of(db: Session, tenant_id: Optional[int], as_of: date, context: Optional[str] = None) -> int:
    """Vehicles whose latest service date is more than 6 months before `as_of`."""
    q = (
        db.query(FleetVehicleRecord.id, func.max(FleetVehicleService.serviced_on))
        .join(FleetVehicleService, FleetVehicleService.vehicle_record_id == FleetVehicleRecord.id)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleService.is_deleted.isnot(True))
        .filter(FleetVehicleService.serviced_on.isnot(None))
        .group_by(FleetVehicleRecord.id)
    )
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    q = _ctx(q, context)
    return sum(1 for _, serviced_on in q.all() if serviced_on and serviced_on + timedelta(days=182) < as_of)


def _delta(now: float, prev: float, higher_is_better: bool = True) -> Tuple[str, bool]:
    """Return (percent-change-magnitude as '6.4', is-this-a-good-move)."""
    if prev == 0:
        pct = 0.0 if now == 0 else 100.0
    else:
        pct = abs((now - prev) / prev * 100)
    improved = (now >= prev) if higher_is_better else (now <= prev)
    return f"{pct:.1f}", improved


_STATUS_ORDER = ["Available", "On Hire", "In Service", "In Repair", "For Sale",
                 "Off Fleet", "Awaiting Plating", "Awaiting De Fleet"]


def _norm_reg(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


# Canonical status so equivalent raw values merge into the Vehicle Details availability
# labels — "on hire"/"on_hire" → "On Hire", "off_hire"/"off fleet" → "Off Fleet", etc.
def _canonical_status(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower().replace("_", " ")
    if not s:
        return "Available"
    if s in ("on hire", "weekly hire"):
        return "On Hire"
    if s in ("off hire", "off fleet"):
        return "Off Hire"
    if s == "in service":
        return "In Service"
    if "repair" in s:
        return "In Repair"
    if s == "for sale":
        return "For Sale"
    if s == "awaiting plating":
        return "Awaiting Plating"
    if s in ("awaiting de fleet", "awaiting de-fleet"):
        return "Awaiting De Fleet"
    if s == "available":
        return "Available"
    return " ".join(w.capitalize() for w in s.split())


_off_hired_column_ready = False


def _ensure_off_hired_column(db: Session) -> None:
    """Add fleet_vehicle_record.off_hired_on if missing (idempotent). This Fleet slice
    has no alembic, so the column that powers the 'off-hired today' filter self-heals."""
    global _off_hired_column_ready
    if _off_hired_column_ready:
        return
    try:
        db.execute(text("ALTER TABLE fleet_vehicle_record ADD COLUMN IF NOT EXISTS off_hired_on DATE"))
        db.commit()
    except Exception:
        db.rollback()
    _off_hired_column_ready = True


def _effective_vehicle_list(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> list:
    """Union of Vehicle Management records and hire vehicles, keyed by registration, each
    carrying its *effective* status. A vehicle currently on hire (from fleet_hire_vehicle)
    reads "On Hire" regardless of its stored vehicle_status; an off-hired vehicle reads
    its own status (Available). Shared source for the status donut and the "Skyline
    Vehicles" list, so they agree.

    When `context` is given (a VM side — cams / skyline) the list is that side's records
    only: the hire overlay then just marks those records On Hire and never introduces a
    hire vehicle that isn't one of the side's cars."""
    _ensure_off_hired_column(db)
    by_reg: dict = {}

    q = db.query(FleetVehicleRecord).filter(FleetVehicleRecord.is_deleted.isnot(True))
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    q = _ctx(q, context)
    for v in q.all():
        n = _norm_reg(v.registration_number)
        if not n:
            continue
        by_reg[n] = {
            "registration": (v.registration_number or "").strip() or "—",
            "make": v.make, "model": v.model,
            "status": _canonical_status(v.vehicle_status),
            "hire_id": None, "driver": None, "hire_start": None, "reference": None,
            "off_hired_on": v.off_hired_on,
        }

    # Overlay hire vehicles — on_hire wins over off_hire wins over the record status.
    hv_q = (
        db.query(FleetHireVehicle, FleetHire)
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        hv_q = hv_q.filter(FleetHire.tenant_id == tenant_id)
    for hv, hire in hv_q.all():
        hs = (hv.hire_status or "").strip().lower()
        if hs != "on_hire":
            continue  # off-hire no longer overlays — an off-hired vehicle reads Available
        n = _norm_reg(hv.registration_number)
        if not n:
            continue
        cur = by_reg.get(n)
        if cur is not None:
            cur["status"] = "On Hire"
            cur["hire_id"] = hire.id
            cur["driver"] = hire.driver_name
            cur["hire_start"] = hv.hire_start_date
            cur["reference"] = hire.fleet_reference
            if not (cur.get("make") or "").strip():
                cur["make"] = hv.make
            if not (cur.get("model") or "").strip():
                cur["model"] = hv.model
        elif not context:
            # Fleet-wide view: a live hire whose reg isn't a stored record still counts.
            # Scoped to a VM side, a non-record hire vehicle isn't one of that side's cars.
            by_reg[n] = {
                "registration": (hv.registration_number or "").strip() or "—",
                "make": hv.make, "model": hv.model, "status": "On Hire",
                "hire_id": hire.id, "driver": hire.driver_name, "hire_start": hv.hire_start_date,
                "reference": hire.fleet_reference, "off_hired_on": None,
            }
    return sorted(by_reg.values(), key=lambda x: x["registration"])


# Every status the donut legend surfaces, in order: the Vehicle Details "Vehicle Status"
# dropdown. Live on-hire vehicles are counted as On Hire; off-hire as Off Fleet.
_DONUT_STATUSES = [
    "Available", "On Hire", "In Service", "In Repair",
    "For Sale", "Off Hire", "Awaiting Plating", "Awaiting De Fleet",
]


def _expiry_dates_by_category(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> dict:
    """{'road_fund'|'plate'|'mot'|'service': [(registration, expiry_date), …]}.
    Road tax lives on the vehicle record, plate/MOT on the licensing authority,
    and 'service due' is derived as the last service date + a 6-month interval."""
    def _scoped(q):
        q = q.filter(FleetVehicleRecord.is_deleted.isnot(True))
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id) if tenant_id is not None else q
        return _ctx(q, context)

    out: dict = {"road_fund": [], "plate": [], "mot": [], "service": []}

    for reg, exp in _scoped(
        db.query(FleetVehicleRecord.registration_number, FleetVehicleRecord.road_tax_expiry_date)
        .filter(FleetVehicleRecord.road_tax_expiry_date.isnot(None))
    ).all():
        out["road_fund"].append((reg, exp))

    auth = _scoped(
        db.query(FleetVehicleRecord.registration_number,
                 FleetVehicleLicensingAuthority.plating_expiry_date,
                 FleetVehicleLicensingAuthority.mot_expiry_date)
        .join(FleetVehicleLicensingAuthority, FleetVehicleLicensingAuthority.vehicle_record_id == FleetVehicleRecord.id)
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
    ).all()
    for reg, plate_exp, mot_exp in auth:
        if plate_exp:
            out["plate"].append((reg, plate_exp))
        if mot_exp:
            out["mot"].append((reg, mot_exp))

    for reg, serviced_on in _scoped(
        db.query(FleetVehicleRecord.registration_number, FleetVehicleService.serviced_on)
        .join(FleetVehicleService, FleetVehicleService.vehicle_record_id == FleetVehicleRecord.id)
        .filter(FleetVehicleService.is_deleted.isnot(True))
        .filter(FleetVehicleService.serviced_on.isnot(None))
    ).all():
        out["service"].append((reg, serviced_on + timedelta(days=182)))  # 6-month service interval

    return out


_COMPLIANCE_TITLES = [("mot", "MOT"), ("plate", "Plate"), ("road_fund", "Road Fund Licence"), ("service", "Service")]


def _remaining_label(expiry: date, today: date):
    days = (expiry - today).days
    if days < 0:
        return "Expired", "red"
    if days == 0:
        return "Today", "gray"
    unit = "day" if days == 1 else "days"
    # Colours match the tab buckets: ≤7 days yellow, everything else under 30 days blue.
    if days <= 7:
        return f"Due in {days} {unit}", "yellow"
    return f"Due in {days} {unit}", "blue"


_EXPIRY_TITLES = [("road_fund", "Road Fund Licence"), ("mot", "MOT Expiry"), ("plate", "Plate Expiry")]


_service_mileage_ready = False


def _ensure_service_mileage_columns(db: Session) -> None:
    """Add the record's current_mileage / service_due_mileage columns if missing —
    the mileage-based Servicing Due widget reads them. Self-heals (no alembic here)."""
    global _service_mileage_ready
    if _service_mileage_ready:
        return
    try:
        db.execute(text("ALTER TABLE fleet_vehicle_record ADD COLUMN IF NOT EXISTS current_mileage INTEGER"))
        db.execute(text("ALTER TABLE fleet_vehicle_record ADD COLUMN IF NOT EXISTS service_due_mileage INTEGER"))
        db.commit()
    except Exception:
        db.rollback()
    _service_mileage_ready = True


_DRIVER_CHECKLIST = [
    ("Bank Statement", "checklist_bank_statement", (), ("bank_statement_",)),
    ("Utility Bill", "checklist_utility_bill", ("firstUtility", "secondUtility", "first_utility", "second_utility"), ("utility_",)),
    ("Driving Licence Front", "checklist_dl_front", ("driving_licence", "dlFront", "dl_front"), ()),
    ("Driving Licence Back", "checklist_dl_back", ("dlBack", "dl_back"), ()),
    ("Taxi Badge", "checklist_taxi_badge", ("taxi_badge",), ()),
    ("Signed Rental Contract", "checklist_signed_rental_contract", (), ()),
    ("Signed Check-Out Sheet", "checklist_signed_checkout_sheet", (), ()),
    ("Signed Check-In Sheet", "checklist_signed_checkin_sheet", (), ()),
]

# Vehicle documents expected on a record (uploaded from its screens): V5C, MOT & Plate
# certificates, and the service invoice. Each row: (label, accepted doc_type values).
_VEHICLE_DOCS = [
    ("V5C Document", {"v5c"}),
    ("MOT Certificate", {"mot"}),
    ("Plate Certificate", {"plating", "plate"}),
    ("Service Invoice", {"service_invoice"}),
]


def _missing_documents(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> list:
    """Every expected-but-not-uploaded vehicle document, one item per record × missing
    doc type. Checks the whole fleet (not only vehicles that already have a licensing
    row), so a record with nothing uploaded lists all of them."""
    from fleet.models.tables import FleetVehicleDocument

    q = db.query(FleetVehicleRecord).filter(FleetVehicleRecord.is_deleted.isnot(True))
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    q = _ctx(q, context)
    records = q.all()
    if not records:
        return []
    ids = [r.id for r in records]
    have: dict = {}
    for rid, dt in (
        db.query(FleetVehicleDocument.vehicle_record_id, FleetVehicleDocument.doc_type)
        .filter(FleetVehicleDocument.vehicle_record_id.in_(ids))
        .all()
    ):
        have.setdefault(rid, set()).add((dt or "").strip().lower())
    items = []
    for r in records:
        reg = (r.registration_number or "").strip() or "—"
        got = have.get(r.id, set())
        for label, accepted in _VEHICLE_DOCS:
            if not (got & accepted):
                items.append({"label": label, "registration": reg, "hire_id": r.hire_id})
    return items


def _missing_driver_documents(db: Session, tenant_id: Optional[int]) -> list:
    """Every expected-but-not-uploaded driver document (the hire's Documents Checklist),
    one item per hire × missing item. Customer Insurance is optional and excluded."""
    from fleet.models.tables import FleetHireDocument

    q = db.query(FleetHire).filter(FleetHire.is_deleted.isnot(True))
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    hires = q.all()
    if not hires:
        return []
    ids = [h.id for h in hires]
    have: dict = {}
    for hid, dt in (
        db.query(FleetHireDocument.hire_id, FleetHireDocument.doc_type)
        .filter(FleetHireDocument.hire_id.in_(ids))
        .all()
    ):
        have.setdefault(hid, set()).add((dt or "").strip())
    # Identify each skyline record by its reference (SK-HR-####) so rows are distinguishable.
    ref_by_hire = {h.id: (h.fleet_reference or "").strip() or (h.driver_name or "").strip() or f"Hire #{h.id}" for h in hires}
    items = []
    for h in hires:
        who = ref_by_hire[h.id]
        got = have.get(h.id, set())
        for label, key, extra, prefixes in _DRIVER_CHECKLIST:
            present = any(
                dt == key or dt in extra or any(dt.startswith(p) for p in prefixes)
                for dt in got
            )
            if not present:
                items.append({"label": label, "registration": who, "hire_id": h.id})

    return items


def _missing_docs_for_side(db: Session, tenant_id: Optional[int], side: str, context: Optional[str] = None) -> list:
    """Skyline → driver documents; Vehicle Management (default) → vehicle documents.
    `context` scopes the vehicle-document check to one VM side (cams / skyline)."""
    if (side or "").strip().lower() == "skyline":
        return _missing_driver_documents(db, tenant_id)
    return _missing_documents(db, tenant_id, context)


_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def _payment_due_date(anchor: Optional[date], payment_day: Optional[str], week: Optional[int]) -> Optional[date]:
    """Derive a weekly payment's due date: anchor + (week-1)*7, then aligned
    forward to the configured payment_day if one is set."""
    if not anchor or not week:
        return None
    due = anchor + timedelta(days=(week - 1) * 7)
    target = _WEEKDAYS.get((payment_day or "").strip().lower())
    if target is not None:
        due += timedelta(days=(target - due.weekday()) % 7)
    return due


def get_weekly_payments(db: Session, tenant_id: Optional[int]) -> dict:
    """Cross-hire weekly payment schedule for the dashboard. Buckets every weekly
    payment by its derived due date into Due Today / Due This Week / Overdue /
    Received Today, and returns the actionable (owed) rows for the table."""
    week_end = date.today() + timedelta(days=7)
    today = date.today()

    q = (
        db.query(FleetHirePayment, FleetHire, FleetHireVehicle)
        .join(FleetHire, FleetHirePayment.hire_id == FleetHire.id)
        .outerjoin(FleetHireVehicle, FleetHirePayment.vehicle_id == FleetHireVehicle.id)
        .filter(FleetHire.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)

    # Rows are grouped by bucket so the dashboard tabs can filter to one bucket.
    buckets: dict = {"due_today": [], "due_this_week": [], "overdue": [], "received_today": [], "all": []}

    hstatus = "—"  # per-payment hire status; _row captures it via closure (set each iteration)

    def _row(reg, cust, due_amt, outstanding, due, label, tone):
        return (due, [reg, cust, f"£{due_amt:,.2f}", f"£{outstanding:,.2f}",
                      due.strftime("%d %b %Y") if due else "—", [label, tone], hstatus])

    # Left-panel summary: money owed by bucket + received so far this week + a
    # per-weekday received breakdown for the mini chart.
    # "Received" window: rolling last 7 days, so the graph always shows a full week of
    # context regardless of today's weekday (a calendar Mon→today window is empty on Monday).
    week_start = today - timedelta(days=6)
    amt = {"overdue": 0.0, "due_today": 0.0, "due_this_week": 0.0, "received": 0.0}
    by_day = [0.0] * 7           # received per weekday (this week)
    by_day_overdue = [0.0] * 7   # overdue outstanding, bucketed by due-date weekday

    for pay, hire, veh in q.all():
        due = _payment_due_date(hire.payment_hire_start_date, hire.payment_day, pay.week)
        due_amt = _to_float(pay.due_amount)
        paid = _to_float(pay.paid_amount)
        outstanding = max(0.0, due_amt - paid)
        reg = veh.registration_number if veh else "—"
        cust = hire.driver_name or "—"
        hstatus = {"on_hire": "On Hire", "off_hire": "Off Hire"}.get((veh.hire_status or "").strip().lower(), "—") if veh else "—"

        # "Received" = paid at some point this week (Mon→today), not just literally today,
        # so the Received tab reflects the week's activity and feeds the graph's green curve.
        if pay.payment_date and week_start <= pay.payment_date <= today:
            buckets["received_today"].append(_row(reg, cust, due_amt, outstanding, due, "Received", "green"))
            amt["received"] += paid
            by_day[pay.payment_date.weekday()] += paid
        owed = (pay.status or "").strip().lower() != "received"
        if owed and due:
            if due == today:
                buckets["due_today"].append(_row(reg, cust, due_amt, outstanding, due, "Due Today", "gray"))
                amt["due_today"] += outstanding
            elif today < due <= week_end:
                buckets["due_this_week"].append(_row(reg, cust, due_amt, outstanding, due, "Due This Week", "yellow"))
                amt["due_this_week"] += outstanding
            elif due < today:
                buckets["overdue"].append(_row(reg, cust, due_amt, outstanding, due, "Overdue", "red"))
                amt["overdue"] += outstanding
                by_day_overdue[due.weekday()] += outstanding

    # "All" = every actionable payment (the four buckets), not the full historical/future
    # schedule — otherwise it balloons to every weekly installment ever recorded.
    buckets["all"] = buckets["overdue"] + buckets["due_today"] + buckets["due_this_week"] + buckets["received_today"]

    total = amt["overdue"] + amt["due_today"] + amt["due_this_week"] + amt["received"]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return {
        "tabs": {k: len(v) for k, v in buckets.items()},
        "rows": {k: [r[1] for r in sorted(v, key=lambda x: (x[0] or today))][: (1000 if k == "all" else 10)] for k, v in buckets.items()},
        "summary": {
            "total": f"£{total:,.0f}",
            "overdue": f"£{amt['overdue']:,.0f}",
            "due_today": f"£{amt['due_today']:,.0f}",
            "received": f"£{amt['received']:,.0f}",
            "by_day": [{"day": d, "amount": round(r), "overdue": round(o)} for d, r, o in zip(day_names, by_day, by_day_overdue)],
        },
    }


def _ensure_snapshot_table(db: Session) -> None:
    from fleet.models.tables import FleetAvailabilitySnapshot
    try:
        FleetAvailabilitySnapshot.__table__.create(bind=db.get_bind(), checkfirst=True)
    except Exception:
        db.rollback()


def _record_availability_snapshot(db: Session, tenant_id: Optional[int], available_now: int, total: int) -> None:
    """Upsert today's availability snapshot (one row per tenant per day) so the
    month-over-month comparison can use real history instead of an estimate."""
    from fleet.models.tables import FleetAvailabilitySnapshot
    _ensure_snapshot_table(db)
    try:
        row = (
            db.query(FleetAvailabilitySnapshot)
            .filter(FleetAvailabilitySnapshot.tenant_id == tenant_id)
            .filter(FleetAvailabilitySnapshot.snapshot_date == date.today())
            .first()
        )
        if row is None:
            db.add(FleetAvailabilitySnapshot(
                tenant_id=tenant_id, snapshot_date=date.today(),
                available_count=available_now, total_count=total,
            ))
        else:
            row.available_count = available_now
            row.total_count = total
        db.commit()
    except Exception:
        db.rollback()


def _availability_pct_as_of(db: Session, tenant_id: Optional[int], as_of: date) -> Optional[int]:
    """Availability % from the snapshot on/just-before ``as_of`` — None if no snapshot
    that old exists yet (history still building up)."""
    from fleet.models.tables import FleetAvailabilitySnapshot
    _ensure_snapshot_table(db)
    row = (
        db.query(FleetAvailabilitySnapshot)
        .filter(FleetAvailabilitySnapshot.tenant_id == tenant_id)
        .filter(FleetAvailabilitySnapshot.snapshot_date <= as_of)
        .order_by(FleetAvailabilitySnapshot.snapshot_date.desc())
        .first()
    )
    if row is None or not row.total_count:
        return None
    return round(row.available_count / row.total_count * 100)


def _overdue_returns_count(db: Session, tenant_id: Optional[int]) -> int:
    q = (
        db.query(func.count(FleetHireVehicle.id))
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(func.lower(func.coalesce(FleetHireVehicle.hire_status, "")) == "on_hire")
        .filter(FleetHireVehicle.hire_end_date.isnot(None))
        .filter(FleetHireVehicle.hire_end_date < date.today())
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    return q.scalar() or 0


def _overdue_tasks_count(db: Session, tenant_id: Optional[int], module: Optional[str] = None, as_of: Optional[date] = None) -> int:
    from libdata.models.tables import Task
    cutoff = as_of or date.today()
    q = (
        db.query(func.count(Task.id))
        .filter(Task.is_deleted.is_(False))
        .filter(Task.due_date.isnot(None))
        .filter(Task.due_date < cutoff)
        .filter(func.lower(func.coalesce(Task.status, "")) != "completed")
    )
    if tenant_id is not None:
        q = q.filter(Task.tenant_id == tenant_id)
    if module:
        q = q.filter(func.lower(func.trim(func.coalesce(Task.module, ""))) == module.strip().lower())
    return q.scalar() or 0


def get_stats(db: Session, tenant_id: Optional[int], period: str = "MTD", module: Optional[str] = None) -> dict:
    """The four top stat cards. `period` (WTD | MTD | YTD) scopes the income
    window and sets the trend comparison to one week / month / year ago. Each
    card carries a stable `key` the frontend maps to its icon; `up` means the
    change was favourable (for Urgent Alerts, fewer is favourable)."""
    period = (period or "MTD").upper()
    if period not in ("TDY", "WTD", "MTD", "YTD"):
        period = "MTD"
    today = date.today()
    now_end = today + timedelta(days=1)

    if period == "TDY":
        win_start, compare = today, "vs yesterday"
    elif period == "WTD":
        win_start, compare = today - timedelta(days=today.weekday()), "vs last week"
    elif period == "YTD":
        win_start, compare = date(today.year, 1, 1), "vs last year"
    else:
        win_start, compare = today.replace(day=1), "vs last month"

    prev_asof = _shift_period(today, period)
    prev_win_start = _shift_period(win_start, period)

    # Vehicle Management is its own module now, one per side: "vehicles_cams" /
    # "vehicles_skyline". Everything past "vehicles_" is the VM side (context) the
    # vehicle metrics scope to; the plain Skyline dashboard passes module "skyline"
    # (no VM context → fleet-wide figures).
    module_l = (module or "").strip().lower()
    is_vm = module_l.startswith("vehicles")
    ctx = _normalise_context(module_l) if is_vm else None

    # "Vehicles on Hire" = how many vehicles are on hire right now (matches the
    # "of N active vehicles" sub-label + the utilisation card), not a daily event count.
    _eff = _effective_vehicle_list(db, tenant_id, ctx)
    current_on_hire_now = sum(1 for v in _eff if v["status"] == "On Hire")
    current_on_hire_prev = _on_hire_as_of(db, tenant_id, prev_asof, ctx)
    total = _fleet_total(db, tenant_id, ctx)
    income_now = _income_between(db, tenant_id, win_start, now_end)
    income_prev = _income_between(db, tenant_id, prev_win_start, win_start)
    # Urgent Alerts — side-aware. Vehicle Management counts overdue MOT, plate,
    # road licence, service, and overdue VM tasks for that side's cars.
    # Skyline = overdue returns + overdue payments + overdue tasks.
    if is_vm:
        vm_task_module = f"vehicles_{ctx}" if ctx else "vehicles"
        urgent_now = (
            _overdue_expiries_as_of(db, tenant_id, today, ctx)
            + _overdue_service_as_of(db, tenant_id, today, ctx)
            + _overdue_tasks_count(db, tenant_id, vm_task_module, today)
        )
        urgent_prev = (
            _overdue_expiries_as_of(db, tenant_id, prev_asof, ctx)
            + _overdue_service_as_of(db, tenant_id, prev_asof, ctx)
            + _overdue_tasks_count(db, tenant_id, vm_task_module, prev_asof)
        )
    else:
        urgent_now = (
            _overdue_returns_count(db, tenant_id)
            + get_weekly_payments(db, tenant_id)["tabs"]["overdue"]
            + _overdue_tasks_count(db, tenant_id, module)
        )
        urgent_prev = urgent_now

    # Fleet Utilization = every vehicle NOT on hire and NOT for sale, over the total fleet.
    util_count = sum(1 for v in _eff if v["status"] not in ("On Hire", "For Sale"))
    util_now = round(util_count / total * 100) if total else 0
    # Record today's snapshot, then compare against the real snapshot from ~a period ago.
    # Until that much history exists, estimate the prior figure from the on-hire delta
    # (a vehicle going on hire leaves the utilised set). Scoped VM views don't touch the
    # tenant-wide snapshot.
    if ctx:
        util_prev_pct = None
    else:
        _record_availability_snapshot(db, tenant_id, util_count, total)
        util_prev_pct = _availability_pct_as_of(db, tenant_id, prev_asof)
    if util_prev_pct is None:
        util_prev = max(0, util_count + (current_on_hire_now - current_on_hire_prev))
        util_prev_pct = round(util_prev / total * 100) if total else 0

    oh_pct, oh_up = _delta(current_on_hire_now, current_on_hire_prev)
    inc_pct, inc_up = _delta(income_now, income_prev)
    av_pct, av_up = _delta(util_now, util_prev_pct)
    ur_pct, ur_up = _delta(urgent_now, urgent_prev, higher_is_better=False)

    # Sub-labels + progress bars for the Fleet Performance card.
    period_sub = {"TDY": "Today", "WTD": "Week to date", "MTD": "Month to date", "YTD": "Year to date"}.get(period, "Month to date")
    oh_progress = round(current_on_hire_now / total * 100) if total else 0
    inc_progress = max(0, min(100, round(50 + (float(inc_pct) if inc_up else -float(inc_pct)) / 2)))

    return {
        "period": period,
        "compare_label": compare,
        "cards": [
            {"key": "vehicles_on_hire", "label": "Vehicles on Hire", "value": str(current_on_hire_now), "pct": oh_pct, "up": oh_up,
             "sub": f"of {total} active vehicles", "progress": oh_progress},
            {"key": "net_income", "label": f"Net Income ({period})", "value": f"£{income_now:,.0f}", "pct": inc_pct, "up": inc_up,
             "sub": period_sub, "progress": inc_progress},
            {"key": "fleet_availability", "label": "Fleet Utilization", "value": f"{util_now}%", "pct": av_pct, "up": av_up,
             "sub": f"{util_count} of {total} vehicles", "progress": util_now},
            {"key": "urgent_alerts", "label": "Urgent Alerts", "value": str(urgent_now), "pct": ur_pct, "up": ur_up,
             "sub": "needs action", "progress": 0},
        ],
    }

