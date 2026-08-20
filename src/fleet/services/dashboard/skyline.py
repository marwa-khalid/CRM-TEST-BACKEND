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

def get_hire_trend(
    db: Session,
    tenant_id: Optional[int],
    period: str = "WTD",
    mode: str = "",
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    cmp_type: str = "",
    a: str = "",
    b: str = "",
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
    # On/Off Hire series for the two adjacent bars — independent of the Status
    # filter — used by both the period views and the YoY / MoM / Custom compares.
    dates_on = _hire_start_dates(db, tenant_id, "on_hire")
    dates_off = _hire_start_dates(db, tenant_id, "off_hire")

    # ── Comparison modes: two totals, previous vs current ─────────────────────
    if mode == "MOM":
        cur = today.replace(day=1)
        prev = _add_months(cur, -1)
        nxt = _add_months(cur, 1)
        return {
            "labels": [_month_label(prev), _month_label(cur)],
            "values": [_count_between(dates_on, prev, cur), _count_between(dates_on, cur, nxt)],
            "values_off": [_count_between(dates_off, prev, cur), _count_between(dates_off, cur, nxt)],
            "caption": f"{_month_label(prev)} vs {_month_label(cur, True)}",
            "comparison_note": "from last month",
        }
    if mode == "YOY":
        cur_start = date(today.year, 1, 1)
        prev_start = date(today.year - 1, 1, 1)
        nxt_start = date(today.year + 1, 1, 1)
        return {
            "labels": [str(today.year - 1), str(today.year)],
            "values": [_count_between(dates_on, prev_start, cur_start), _count_between(dates_on, cur_start, nxt_start)],
            "values_off": [_count_between(dates_off, prev_start, cur_start), _count_between(dates_off, cur_start, nxt_start)],
            "caption": f"{today.year - 1} vs {today.year}",
            "comparison_note": "from last year",
        }

    # ── Custom Year/Month comparison: two chosen periods, side by side ────────
    if period == "CUSTOM" and cmp_type and a and b:
        ct = cmp_type.strip().lower()
        try:
            if ct == "year":
                ya, yb = int(a), int(b)
                ra = (date(ya, 1, 1), date(ya + 1, 1, 1))
                rb = (date(yb, 1, 1), date(yb + 1, 1, 1))
                la, lb = str(ya), str(yb)
            else:  # month, a/b are "YYYY-MM"
                sa = date(int(a[:4]), int(a[5:7]), 1)
                sb = date(int(b[:4]), int(b[5:7]), 1)
                ra = (sa, _add_months(sa, 1))
                rb = (sb, _add_months(sb, 1))
                la, lb = _month_label(sa, True), _month_label(sb, True)
            return {
                "labels": [la, lb],
                "values": [_count_between(dates_on, *ra), _count_between(dates_on, *rb)],
                "values_off": [_count_between(dates_off, *ra), _count_between(dates_off, *rb)],
                "caption": f"{la} vs {lb}",
                "comparison_note": f"vs {la}",
            }
        except (ValueError, IndexError):
            pass

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
            labels.append(f"Week {wk}")
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

    # Period views show two adjacent bars per bucket: On Hire and Off Hire counts,
    # side by side (independent of the Status filter, which still scopes the
    # comparison modes above via ``dates``).
    dates_on = _hire_start_dates(db, tenant_id, "on_hire")
    dates_off = _hire_start_dates(db, tenant_id, "off_hire")
    return {
        "labels": labels,
        "values": [_count_between(dates_on, s, e) for s, e in ranges],
        "values_off": [_count_between(dates_off, s, e) for s, e in ranges],
        "caption": caption,
        "comparison_note": None,
    }


# ── Top stat cards ────────────────────────────────────────────────────────────
def get_missing_documents(db: Session, tenant_id: Optional[int], side: str = "vehicles", context: Optional[str] = None) -> dict:
    """Full list of missing documents for the Attention slider — vehicle docs for
    Vehicle Management, driver docs (driving licence / taxi badge) for Skyline."""
    return {"items": _missing_docs_for_side(db, tenant_id, side, context)}


def get_attention(db: Session, tenant_id: Optional[int], side: str = "vehicles", context: Optional[str] = None) -> dict:
    """The three Attention-Required tiles: vehicles out past their return date,
    documents missing (vehicle docs for VM / driver docs for Skyline), and hire
    payments past due."""
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
        "missing_documents": len(_missing_docs_for_side(db, tenant_id, side, context)),
        "overdue_payments": get_weekly_payments(db, tenant_id)["tabs"]["overdue"],
    }


def get_overdue_returns(db: Session, tenant_id: Optional[int]) -> dict:
    """Detail rows for the Overdue Returns slider: vehicles still on hire whose
    expected return date has passed. Mirrors the count in ``get_attention``."""
    today = date.today()
    q = (
        db.query(FleetHireVehicle, FleetHire)
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(func.lower(func.coalesce(FleetHireVehicle.hire_status, "")) == "on_hire")
        .filter(FleetHireVehicle.hire_end_date.isnot(None))
        .filter(FleetHireVehicle.hire_end_date < today)
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    items = []
    for veh, hire in q.order_by(FleetHireVehicle.hire_end_date.asc()).all():
        end = veh.hire_end_date
        days = (today - end).days if end else 0
        model = " ".join(x for x in [veh.make, veh.model] if x)
        items.append({
            "registration": veh.registration_number or "—",
            "model": model or "—",
            "driver": (hire.driver_name or "").strip() or "—",
            "due_date": end.strftime("%d %b %Y") if end else "—",
            "days_overdue": days,
            "hire_id": hire.id,
        })
    return {"items": items}


def get_overdue_payments(db: Session, tenant_id: Optional[int]) -> dict:
    """Detail rows for the Overdue Payments slider: owed weekly payments whose
    derived due date has passed. Mirrors the count in ``get_attention``."""
    today = date.today()
    q = (
        db.query(FleetHirePayment, FleetHire, FleetHireVehicle)
        .join(FleetHire, FleetHirePayment.hire_id == FleetHire.id)
        .outerjoin(FleetHireVehicle, FleetHirePayment.vehicle_id == FleetHireVehicle.id)
        .filter(FleetHire.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    items = []
    for pay, hire, veh in q.all():
        if (pay.status or "").strip().lower() == "received":
            continue
        due = _payment_due_date(hire.payment_hire_start_date, hire.payment_day, pay.week)
        if not (due and due < today):
            continue
        due_amt = _to_float(pay.due_amount)
        paid = _to_float(pay.paid_amount)
        outstanding = max(0.0, due_amt - paid)
        items.append({
            "registration": (veh.registration_number if veh else "—") or "—",
            "driver": (hire.driver_name or "").strip() or "—",
            "amount": f"£{outstanding:,.2f}",
            "due_date": due.strftime("%d %b %Y"),
            "days_overdue": (today - due).days,
            "hire_id": hire.id,
        })
    items.sort(key=lambda x: -x["days_overdue"])
    return {"items": items}


