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

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from fleet.models.tables import (
    FleetHire,
    FleetHirePayment,
    FleetHireVehicle,
    FleetVehicleLicensingAuthority,
    FleetVehicleRecord,
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


def get_hire_trend(
    db: Session,
    tenant_id: Optional[int],
    period: str = "WTD",
    mode: str = "",
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """Vehicle-hire counts for the Fleet dashboard's Hire Trend graph.

    ``period`` is WTD | MTD | YTD | CUSTOM; ``mode`` YOY | MOM turns it into a
    two-bar previous-vs-current comparison. The response mirrors the chart's own
    shape so the frontend maps it straight onto a view:
    ``{labels, values, caption, comparison_note}``.
    """
    period = (period or "WTD").upper()
    mode = (mode or "").upper()
    today = date.today()
    dates = _hire_start_dates(db, tenant_id, status)

    # ── Comparison modes: two totals, previous vs current ─────────────────────
    if mode == "MOM":
        cur = today.replace(day=1)
        prev = _add_months(cur, -1)
        nxt = _add_months(cur, 1)
        return {
            "labels": [_month_label(prev), _month_label(cur)],
            "values": [_count_between(dates, prev, cur), _count_between(dates, cur, nxt)],
            "caption": f"{_month_label(prev)} vs {_month_label(cur, True)}",
            "comparison_note": "from last month",
        }
    if mode == "YOY":
        cur_start = date(today.year, 1, 1)
        prev_start = date(today.year - 1, 1, 1)
        nxt_start = date(today.year + 1, 1, 1)
        return {
            "labels": [str(today.year - 1), str(today.year)],
            "values": [_count_between(dates, prev_start, cur_start), _count_between(dates, cur_start, nxt_start)],
            "caption": f"{today.year - 1} vs {today.year}",
            "comparison_note": "from last year",
        }

    # ── Period buckets ────────────────────────────────────────────────────────
    labels: List[str] = []
    ranges: List[tuple] = []
    caption = ""

    if period == "WTD":
        monday = today - timedelta(days=today.weekday())
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri"]  # working week only
        ranges = [(monday + timedelta(days=i), monday + timedelta(days=i + 1)) for i in range(5)]
        caption = f"{monday:%d-%m-%y} to {monday + timedelta(days=4):%d-%m-%y}"
    elif period == "MTD":
        first = today.replace(day=1)
        month_end = _add_months(first, 1)
        wk, cursor = 1, first
        while cursor < month_end:
            ranges.append((cursor, min(cursor + timedelta(days=7), month_end)))
            labels.append(f"W{wk}")
            cursor += timedelta(days=7)
            wk += 1
        caption = _month_label(first, True)
    elif period == "CUSTOM":
        s_d = _parse_date(start)
        e_d = _parse_date(end)
        if not (s_d and e_d and e_d >= s_d):
            # No range picked yet → default to the last 6 weeks.
            e_d, s_d = today, today - timedelta(weeks=6)
        if (e_d - s_d).days <= 45:
            cursor = s_d
            while cursor <= e_d:
                labels.append(f"{cursor.day} {_MONTHS[cursor.month - 1]}")
                ranges.append((cursor, cursor + timedelta(days=1)))
                cursor += timedelta(days=1)
        else:
            end_excl = e_d + timedelta(days=1)
            cursor = s_d.replace(day=1)
            while cursor < end_excl:
                nxt = _add_months(cursor, 1)
                labels.append(_month_label(cursor, True))
                ranges.append((cursor, min(nxt, end_excl)))
                cursor = nxt
        caption = f"{s_d:%d %b} – {e_d:%d %b %Y}"
    else:  # YTD → Jan through the current month
        for m in range(1, today.month + 1):
            s = date(today.year, m, 1)
            ranges.append((s, _add_months(s, 1)))
            labels.append(_MONTHS[m - 1])
        caption = f"{_MONTHS[0]}–{_MONTHS[today.month - 1]} {today.year}"

    return {
        "labels": labels,
        "values": [_count_between(dates, s, e) for s, e in ranges],
        "caption": caption,
        "comparison_note": None,
    }


# ── Top stat cards ────────────────────────────────────────────────────────────
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


def _on_hire_as_of(db: Session, tenant_id: Optional[int], as_of: date) -> int:
    """Vehicles under an active hire on `as_of` (started on/before, not yet ended)."""
    q = (
        db.query(func.count(FleetHireVehicle.id))
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(FleetHireVehicle.hire_start_date.isnot(None))
        .filter(FleetHireVehicle.hire_start_date <= as_of)
        .filter(or_(FleetHireVehicle.hire_end_date.is_(None), FleetHireVehicle.hire_end_date >= as_of))
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    return q.scalar() or 0


def _fleet_total(db: Session, tenant_id: Optional[int]) -> int:
    q = db.query(func.count(FleetVehicleRecord.id)).filter(FleetVehicleRecord.is_deleted.isnot(True))
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    return q.scalar() or 0


def _available_count(db: Session, tenant_id: Optional[int]) -> int:
    """Vehicles whose status is 'Available' (same source as the donut)."""
    q = db.query(func.count(FleetVehicleRecord.id)).filter(
        FleetVehicleRecord.is_deleted.isnot(True),
        func.lower(func.coalesce(FleetVehicleRecord.vehicle_status, "")) == "available",
    )
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    return q.scalar() or 0


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


def _overdue_expiries_as_of(db: Session, tenant_id: Optional[int], as_of: date) -> int:
    """Road-tax / plate / MOT expiries already lapsed on `as_of`."""
    rt = db.query(func.count(FleetVehicleRecord.id)).filter(
        FleetVehicleRecord.is_deleted.isnot(True),
        FleetVehicleRecord.road_tax_expiry_date.isnot(None),
        FleetVehicleRecord.road_tax_expiry_date < as_of,
    )
    if tenant_id is not None:
        rt = rt.filter(FleetVehicleRecord.tenant_id == tenant_id)

    authority = (
        db.query(FleetVehicleLicensingAuthority)
        .join(FleetVehicleRecord, FleetVehicleLicensingAuthority.vehicle_record_id == FleetVehicleRecord.id)
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        authority = authority.filter(FleetVehicleRecord.tenant_id == tenant_id)
    plate = authority.filter(
        FleetVehicleLicensingAuthority.plating_expiry_date.isnot(None),
        FleetVehicleLicensingAuthority.plating_expiry_date < as_of,
    ).count()
    mot = authority.filter(
        FleetVehicleLicensingAuthority.mot_expiry_date.isnot(None),
        FleetVehicleLicensingAuthority.mot_expiry_date < as_of,
    ).count()
    return (rt.scalar() or 0) + plate + mot


def _delta(now: float, prev: float, higher_is_better: bool = True) -> Tuple[str, bool]:
    """Return (percent-change-magnitude as '6.4', is-this-a-good-move)."""
    if prev == 0:
        pct = 0.0 if now == 0 else 100.0
    else:
        pct = abs((now - prev) / prev * 100)
    improved = (now >= prev) if higher_is_better else (now <= prev)
    return f"{pct:.1f}", improved


_STATUS_ORDER = ["Available", "On Hire", "In Repair", "Off Fleet", "Awaiting Plating", "Awaiting De-fleet"]


def get_vehicle_status(db: Session, tenant_id: Optional[int]) -> dict:
    """Vehicle-status distribution for the donut. Groups fleet_vehicle_record by
    vehicle_status (blank/null statuses excluded); known statuses come first in a
    stable order, any others follow. Returns {total, segments:[{label, value}]}."""
    q = db.query(FleetVehicleRecord.vehicle_status, func.count(FleetVehicleRecord.id)).filter(
        FleetVehicleRecord.is_deleted.isnot(True)
    )
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    counts: dict = {}
    for status, n in q.group_by(FleetVehicleRecord.vehicle_status).all():
        label = (status or "").strip()
        if label:
            counts[label] = counts.get(label, 0) + n
    segments = [{"label": s, "value": counts.pop(s)} for s in _STATUS_ORDER if s in counts]
    segments += [{"label": s, "value": n} for s, n in counts.items()]
    return {"total": sum(s["value"] for s in segments), "segments": segments}


# ── Compliance + expiry cards (Road Fund / Plate / MOT / Service) ─────────────
def _expiry_dates_by_category(db: Session, tenant_id: Optional[int]) -> dict:
    """{'road_fund'|'plate'|'mot'|'service': [(registration, expiry_date), …]}.
    Road tax lives on the vehicle record, plate/MOT on the licensing authority,
    and 'service due' is derived as the last service date + a 6-month interval."""
    def _scoped(q):
        q = q.filter(FleetVehicleRecord.is_deleted.isnot(True))
        return q.filter(FleetVehicleRecord.tenant_id == tenant_id) if tenant_id is not None else q

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


def get_compliance(db: Session, tenant_id: Optional[int]) -> dict:
    """Per-category compliance: overdue count, % overdue (bar), and counts due
    within 7 and within 30 days."""
    today = date.today()
    cats = _expiry_dates_by_category(db, tenant_id)
    result = []
    for key, title in _COMPLIANCE_TITLES:
        items = cats.get(key, [])
        total = len(items) or 1
        overdue = sum(1 for _, e in items if e < today)
        d7 = sum(1 for _, e in items if today <= e <= today + timedelta(days=7))
        d30 = sum(1 for _, e in items if today <= e <= today + timedelta(days=30))
        result.append({
            "key": key, "title": title,
            "overdue": overdue, "bar": round(overdue / total * 100), "d7": d7, "d30": d30,
        })
    return {"categories": result}


def _remaining_label(expiry: date, today: date):
    days = (expiry - today).days
    if days < 0:
        return "Expired", "red"
    if days == 0:
        return "Today", "orange"
    if days <= 7:
        return f"{days} days", "orange"
    return f"{days} days", "green"


_EXPIRY_TITLES = [("road_fund", "Road Fund Licence"), ("mot", "MOT Expiry"), ("plate", "Plate Expiry")]


def get_expiries(db: Session, tenant_id: Optional[int]) -> dict:
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

    cats = _expiry_dates_by_category(db, tenant_id)
    cards: dict = {}
    for key, _title in _EXPIRY_TITLES:
        items = sorted(cats.get(key, []), key=lambda x: x[1])
        rows: dict = {"expired": [], "today": [], "d7": [], "d30": []}
        for reg, e in items:
            bucket = _bucket(e)
            if bucket:
                rows[bucket].append([reg or "—", e.strftime("%d %b %Y"), list(_remaining_label(e, today))])
        cards[key] = {
            "tabs": {k: len(v) for k, v in rows.items()},
            "rows": {k: v[:50] for k, v in rows.items()},  # full set for the slider; card shows first 5
        }
    return cards


def _missing_documents(db: Session, tenant_id: Optional[int]) -> list:
    """One item per missing required certificate (MOT / Plate) on a vehicle,
    with the vehicle registration and its hire for click-through."""
    q = (
        db.query(
            FleetVehicleRecord.registration_number,
            FleetVehicleRecord.hire_id,
            FleetVehicleLicensingAuthority.mot_certificate_name,
            FleetVehicleLicensingAuthority.plating_certificate_name,
        )
        .join(FleetVehicleLicensingAuthority, FleetVehicleLicensingAuthority.vehicle_record_id == FleetVehicleRecord.id)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        q = q.filter(FleetVehicleRecord.tenant_id == tenant_id)
    items = []
    for reg, hire_id, mot_cert, plate_cert in q.all():
        if not (mot_cert or "").strip():
            items.append({"label": "MOT Certificate", "registration": reg or "—", "hire_id": hire_id})
        if not (plate_cert or "").strip():
            items.append({"label": "Plate Certificate", "registration": reg or "—", "hire_id": hire_id})
    return items


def get_missing_documents(db: Session, tenant_id: Optional[int]) -> dict:
    """Full list of vehicles missing a required document (Attention slider)."""
    return {"items": _missing_documents(db, tenant_id)}


def get_attention(db: Session, tenant_id: Optional[int]) -> dict:
    """The three Attention-Required tiles: vehicles out past their return date,
    vehicles missing a required document, and hire payments past due."""
    today = date.today()

    returns_q = (
        db.query(func.count(FleetHireVehicle.id))
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(func.lower(func.coalesce(FleetHireVehicle.hire_status, "")) == "on_hire")
        .filter(FleetHireVehicle.hire_end_date.isnot(None))
        .filter(FleetHireVehicle.hire_end_date < today)
    )
    if tenant_id is not None:
        returns_q = returns_q.filter(FleetHire.tenant_id == tenant_id)

    return {
        "overdue_returns": returns_q.scalar() or 0,
        "missing_documents": len(_missing_documents(db, tenant_id)),
        "overdue_payments": get_weekly_payments(db, tenant_id)["tabs"]["overdue"],
    }


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
    buckets: dict = {"due_today": [], "due_this_week": [], "overdue": [], "received_today": []}

    def _row(reg, cust, due_amt, outstanding, due, label, tone):
        return (due, [reg, cust, f"£{due_amt:,.2f}", f"£{outstanding:,.2f}",
                      due.strftime("%d %b %Y") if due else "—", [label, tone]])

    for pay, hire, veh in q.all():
        due = _payment_due_date(hire.payment_hire_start_date, hire.payment_day, pay.week)
        due_amt = _to_float(pay.due_amount)
        paid = _to_float(pay.paid_amount)
        outstanding = max(0.0, due_amt - paid)
        reg = veh.registration_number if veh else "—"
        cust = hire.driver_name or "—"

        if pay.payment_date == today:
            buckets["received_today"].append(_row(reg, cust, due_amt, outstanding, due, "Received Today", "green"))
        owed = (pay.status or "").strip().lower() != "received"
        if owed and due:
            if due == today:
                buckets["due_today"].append(_row(reg, cust, due_amt, outstanding, due, "Due Today", "orange"))
            elif today < due <= week_end:
                buckets["due_this_week"].append(_row(reg, cust, due_amt, outstanding, due, "Due This Week", "blue"))
            elif due < today:
                buckets["overdue"].append(_row(reg, cust, due_amt, outstanding, due, "Overdue", "red"))

    return {
        "tabs": {k: len(v) for k, v in buckets.items()},
        "rows": {k: [r[1] for r in sorted(v, key=lambda x: (x[0] or today))][:10] for k, v in buckets.items()},
    }


def get_stats(db: Session, tenant_id: Optional[int], period: str = "MTD") -> dict:
    """The four top stat cards. `period` (WTD | MTD | YTD) scopes the income
    window and sets the trend comparison to one week / month / year ago. Each
    card carries a stable `key` the frontend maps to its icon; `up` means the
    change was favourable (for Urgent Alerts, fewer is favourable)."""
    period = (period or "MTD").upper()
    if period not in ("WTD", "MTD", "YTD"):
        period = "MTD"
    today = date.today()
    now_end = today + timedelta(days=1)

    if period == "WTD":
        win_start, compare = today - timedelta(days=today.weekday()), "vs last week"
    elif period == "YTD":
        win_start, compare = date(today.year, 1, 1), "vs last year"
    else:
        win_start, compare = today.replace(day=1), "vs last month"

    prev_asof = _shift_period(today, period)
    prev_win_start = _shift_period(win_start, period)

    on_hire_now, on_hire_prev = _on_hire_as_of(db, tenant_id, today), _on_hire_as_of(db, tenant_id, prev_asof)
    total = _fleet_total(db, tenant_id)
    income_now = _income_between(db, tenant_id, win_start, now_end)
    income_prev = _income_between(db, tenant_id, prev_win_start, win_start)
    urgent_now, urgent_prev = _overdue_expiries_as_of(db, tenant_id, today), _overdue_expiries_as_of(db, tenant_id, prev_asof)

    # Availability = share of the fleet whose status is 'Available' (matches the donut).
    available_now = _available_count(db, tenant_id)
    avail_now = round(available_now / total * 100) if total else 0
    # No history for vehicle_status, so estimate the prior availability by assuming
    # the vehicles that went on hire since then were 'Available' before.
    available_prev = max(0, available_now + (on_hire_now - on_hire_prev))
    avail_prev = round(available_prev / total * 100) if total else 0

    oh_pct, oh_up = _delta(on_hire_now, on_hire_prev)
    inc_pct, inc_up = _delta(income_now, income_prev)
    av_pct, av_up = _delta(avail_now, avail_prev)
    ur_pct, ur_up = _delta(urgent_now, urgent_prev, higher_is_better=False)

    return {
        "period": period,
        "compare_label": compare,
        "cards": [
            {"key": "vehicles_on_hire", "label": "Vehicles on Hire", "value": str(on_hire_now), "pct": oh_pct, "up": oh_up},
            {"key": "net_income", "label": f"Net Income ({period})", "value": f"£{income_now:,.0f}", "pct": inc_pct, "up": inc_up},
            {"key": "fleet_availability", "label": "Fleet Availability", "value": f"{avail_now}%", "pct": av_pct, "up": av_up},
            {"key": "urgent_alerts", "label": "Urgent Alerts", "value": str(urgent_now), "pct": ur_pct, "up": ur_up},
        ],
    }
