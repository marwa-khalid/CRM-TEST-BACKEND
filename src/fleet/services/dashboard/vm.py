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


from fleet.services.dashboard.common import (
    _MONTHS,
    _add_months,
    _month_label,
    _parse_date,
    _count_between,
    _hire_start_dates,
    _to_float,
    _shift_period,
    _normalise_context,
    _vehicle_record_regs_for_context,
    _count_hire_vehicle_rows,
    _on_hire_as_of,
    _on_hire_started_on,
    _ctx,
    _fleet_total,
    _available_count,
    _income_between,
    _overdue_expiries_as_of,
    _overdue_service_as_of,
    _delta,
    _STATUS_ORDER,
    _norm_reg,
    _canonical_status,
    _off_hired_column_ready,
    _ensure_off_hired_column,
    _effective_vehicle_list,
    _DONUT_STATUSES,
    _expiry_dates_by_category,
    _COMPLIANCE_TITLES,
    _remaining_label,
    _EXPIRY_TITLES,
    _service_mileage_ready,
    _ensure_service_mileage_columns,
    _DRIVER_CHECKLIST,
    _VEHICLE_DOCS,
    _missing_documents,
    _missing_driver_documents,
    _missing_docs_for_side,
    _WEEKDAYS,
    _payment_due_date,
    get_weekly_payments,
    _ensure_snapshot_table,
    _record_availability_snapshot,
    _availability_pct_as_of,
    _overdue_returns_count,
    _overdue_tasks_count,
    get_stats,
)

def get_vehicle_status(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> dict:
    """Vehicle-status distribution for the donut: one bucket per Vehicle Details
    availability status. Reads the same effective list the "Skyline Vehicles" section uses
    (records + the live-hire overlay, so an on-hire vehicle reads On Hire and an
    off-hire one Off Fleet) so the two always agree. Every status is emitted (0 included)
    so the legend always lists them all."""
    counts = {k: 0 for k in _DONUT_STATUSES}
    for v in _effective_vehicle_list(db, tenant_id, context):
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    segments = [{"label": k, "value": counts.get(k, 0)} for k in _DONUT_STATUSES]
    # Any status outside the known list (defensive) still shows, after the fixed ones.
    segments += [{"label": k, "value": v} for k, v in counts.items() if k not in _DONUT_STATUSES]
    return {"total": sum(counts.values()), "segments": segments}


def get_fleet_vehicles(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> dict:
    """Live vehicle list for the dashboard's "Skyline Vehicles" section — the same
    effective list the status donut counts (records + hire on/off-hire). On-hire and
    off-hire vehicles read as such (never "Available"), and on-hire carries the driver
    + how long it's been out. Empty when there are no vehicles or hires. ``context``
    (cams | skyline) scopes to one Vehicle Management side."""
    today = date.today()
    items = []
    for v in _effective_vehicle_list(db, tenant_id, context):
        model = " ".join(x for x in [v.get("make"), v.get("model")] if x) or "—"
        s = (v["status"] or "").strip()
        sl = s.lower()
        if s in ("On Hire", "Weekly Hire"):
            key = "hire"
        elif s in ("Off Hire", "Off Fleet"):
            key = "off"
        elif "repair" in sl:
            key = "repair"
        elif s == "For Sale":
            key = "sale"
        elif s == "Available" or not s:
            key = "available"
        else:
            key = "other"  # In Service, Awaiting Plating / De Fleet, etc.
        item = {"registration": v["registration"], "model": model, "statusKey": key, "statusLabel": s or "Available"}
        # Off-hired today (now Available) — powers the daily "Off Hire" filter on the dashboard.
        item["offHiredToday"] = bool(v.get("off_hired_on") and v.get("off_hired_on") == today)
        if key == "hire":
            start = v.get("hire_start")
            if start:
                days = max(0, (today - start).days)
                item["hireInfo"] = f"On Hire for {days} Day{'s' if days != 1 else ''}"
            if (v.get("driver") or "").strip():
                item["customer"] = v["driver"].strip()
            if (v.get("reference") or "").strip():
                item["reference"] = v["reference"].strip()
        items.append(item)
    return {"items": items}


# ── Compliance + expiry cards (Road Fund / Plate / MOT / Service) ─────────────
def get_compliance(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> dict:
    """Per-category compliance: overdue count, % overdue (bar), and counts due
    within 7 and within 30 days."""
    today = date.today()
    cats = _expiry_dates_by_category(db, tenant_id, context)
    result = []
    for key, title in _COMPLIANCE_TITLES:
        items = cats.get(key, [])
        # Service Due should only "count" once it's actually approaching: a vehicle
        # serviced recently (next service months out) falls in no filter window
        # (overdue / 7d / 30d), so it must not inflate the total either.
        if key == "service":
            horizon = today + timedelta(days=30)
            items = [(reg, e) for reg, e in items if e <= horizon]
        total = len(items)
        denom = total or 1
        overdue = sum(1 for _, e in items if e < today)
        d7 = sum(1 for _, e in items if today <= e <= today + timedelta(days=7))
        d30 = sum(1 for _, e in items if today <= e <= today + timedelta(days=30))
        result.append({
            "key": key, "title": title, "total": total,
            "overdue": overdue, "bar": round(overdue / denom * 100), "d7": d7, "d30": d30,
            # % of the fleet whose document isn't overdue — the "Compliant" figure.
            "compliant": round((denom - overdue) / denom * 100),
            "amber": round(d30 / denom * 100),  # at-risk share for the middle bar segment
        })
    return {"categories": result}


def get_expiries(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> dict:
    """Per-category expiry cards. Rows are grouped by bucket (expired / today /
    7 days / 30 days) so the dashboard tabs can filter to a single bucket; tab
    counts are the bucket sizes."""
    today = date.today()
    d7, d30 = today + timedelta(days=7), today + timedelta(days=30)

    def _bucket(e: date):
        if e < today:
            return "expired"
        if e == today:
            return "today"
        if e <= d7:
            return "d7"
        if e <= d30:
            return "d30"
        return None  # further-future expiries aren't surfaced

    cats = _expiry_dates_by_category(db, tenant_id, context)

    # reg -> licensing authority (for the Plate cards/slider, which show the authority
    # in place of a driver).
    authority_by_reg: dict = {}
    aq = (
        db.query(FleetVehicleRecord.registration_number, FleetVehicleLicensingAuthority.licensing_authority)
        .join(FleetVehicleLicensingAuthority, FleetVehicleLicensingAuthority.vehicle_record_id == FleetVehicleRecord.id)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        aq = aq.filter(FleetVehicleRecord.tenant_id == tenant_id)
    aq = _ctx(aq, context)
    for reg, auth in aq.all():
        if reg and auth and reg not in authority_by_reg:
            authority_by_reg[reg] = auth

    # reg -> "make model" for the card subtitle.
    model_by_reg: dict = {}
    mq = db.query(FleetVehicleRecord.registration_number, FleetVehicleRecord.make, FleetVehicleRecord.model).filter(
        FleetVehicleRecord.is_deleted.isnot(True)
    )
    if tenant_id is not None:
        mq = mq.filter(FleetVehicleRecord.tenant_id == tenant_id)
    mq = _ctx(mq, context)
    for reg, make, model in mq.all():
        if reg and reg not in model_by_reg:
            model_by_reg[reg] = " ".join(x for x in [make, model] if x)

    # norm reg -> effective status + current driver, from the SAME effective list the
    # vehicles cards use (records + live hire overlay). Driving both off this list keeps
    # the expiry "hire status" and driver in lockstep with the cards — the vehicle
    # record's hire_id column can be stale, so we never rely on it here.
    status_by_reg: dict = {}
    driver_by_reg: dict = {}
    for v in _effective_vehicle_list(db, tenant_id, context):
        n = _norm_reg(v.get("registration"))
        if n and n not in status_by_reg:
            status_by_reg[n] = v["status"]
            if (v.get("driver") or "").strip():
                driver_by_reg[n] = v["driver"].strip()

    cards: dict = {}
    for key, _title in _EXPIRY_TITLES + [("service", "Service")]:
        items = sorted(cats.get(key, []), key=lambda x: x[1])
        rows: dict = {"expired": [], "today": [], "d7": [], "d30": []}
        for reg, e in items:
            bucket = _bucket(e)
            if bucket:
                # 4th slot: Plate carries the licensing authority, others the driver.
                # 5th slot: "make model" (used by the Plate cards).
                extra = authority_by_reg.get(reg, "—") if key == "plate" else (driver_by_reg.get(_norm_reg(reg)) or "—")
                rows[bucket].append([
                    reg or "—", e.strftime("%d %b %Y"), list(_remaining_label(e, today)),
                    extra, model_by_reg.get(reg, ""), status_by_reg.get(_norm_reg(reg), ""),
                ])
        cards[key] = {
            "tabs": {k: len(v) for k, v in rows.items()},
            "rows": {k: v[:50] for k, v in rows.items()},  # full set for the slider; card shows first 5
        }
    return cards


def get_servicing_due(db: Session, tenant_id: Optional[int], context: Optional[str] = None) -> dict:
    """Servicing Due card — mileage-based (distinct from the date-driven document
    cards). For each vehicle:  remaining = service_due_mileage − current_mileage.
    Bucketed Overdue (past the service odometer) / Due within 500 mi / Due within
    1,000 mi; each row carries the current mileage, the service-due odometer and a
    status label. Vehicles further than 1,000 miles out aren't surfaced."""
    _ensure_service_mileage_columns(db)

    q = (
        db.query(
            FleetVehicleRecord.registration_number,
            FleetVehicleRecord.current_mileage,
            FleetVehicleRecord.service_due_mileage,
        )
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.current_mileage.isnot(None))
        .filter(FleetVehicleRecord.service_due_mileage.isnot(None))
    )
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    q = _ctx(q, context)

    rows: dict = {"overdue": [], "within_500": [], "within_1000": []}
    # Soonest-due first (smallest remaining, i.e. most overdue, at the top).
    computed = [(reg, cur, due, due - cur) for reg, cur, due in q.all()]
    for reg, cur, due, remaining in sorted(computed, key=lambda r: r[3]):
        vreg = reg or "—"
        cur_s, due_s = f"{cur:,}", f"{due:,}"
        if remaining < 0:
            rows["overdue"].append([vreg, cur_s, due_s, [f"{abs(remaining):,} miles overdue", "red"]])
        elif remaining <= 500:
            label = "Service Due" if remaining == 0 else f"{remaining:,} miles remaining"
            rows["within_500"].append([vreg, cur_s, due_s, [label, "orange"]])
        elif remaining <= 1000:
            rows["within_1000"].append([vreg, cur_s, due_s, [f"{remaining:,} miles remaining", "violet"]])
        # remaining > 1,000 → not surfaced

    return {
        "tabs": {k: len(v) for k, v in rows.items()},
        "rows": {k: v[:50] for k, v in rows.items()},
    }


# Driver "Documents Checklist" — the required items (Customer Insurance is Optional and
# excluded). Each row: (label, checklist key, extra accepted doc_types, accepted prefixes).
# Mirrors the frontend DocumentChecklist.matchesChecklistDoc so "uploaded" agrees with the UI.
