"""Dashboard aggregates — real data summed across the tenant's claims.

All financial tables are tenant-scoped by joining to `claims` on claim_id.
Numbers the system can't yet derive (fleet availability / vehicle returns) are
flagged in comments and returned as conservative values; Fleet sections are
static on the frontend per the current design.
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from libdata.models.tables import (
    Claim, VehicleDetail, Storage, ComparisonSettlement,
    HirePaymentDetails, HireDetail, EngineerDetail, Recovery, Task, CaseStatus,
    SourceChannel, DirectHirePayment, ABIBHRCharges, HireVehicleProvided,
    PlatingAdditionalCharges, RouteRepair, Referrer, User,
)

# hire_vehicle_status_id for a vehicle that is currently On Hire.
_ON_HIRE_STATUS = 1

_TERMINAL = ("Completed", "Rejected")
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _f(x) -> float:
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _scoped(q, model, tenant_id):
    q = q.join(Claim, model.claim_id == Claim.id)
    if tenant_id is not None:
        q = q.filter(Claim.tenant_id == tenant_id)
    # Exclude soft-deleted (inactive) claims from every aggregate — they stay in
    # the DB for possible restore but must not count anywhere.
    q = q.filter(Claim.is_deleted.isnot(True))
    return q


def _sum(db: Session, model, expr, tenant_id) -> float:
    q = _scoped(db.query(func.coalesce(func.sum(expr), 0)), model, tenant_id)
    return _f(q.scalar())


def _sum_for_claim_ids(db: Session, model, expr, tenant_id, claim_ids) -> float:
    if claim_ids is not None and not claim_ids:
        return 0.0
    q = _scoped(db.query(func.coalesce(func.sum(expr), 0)), model, tenant_id)
    if claim_ids is not None:
        q = q.filter(model.claim_id.in_(claim_ids))
    return _f(q.scalar())


def _sum_in_period(db, model, expr, tenant_id, start, end) -> float:
    """Sum a column for claims whose file_opened_at falls in [start, end)."""
    q = _scoped(db.query(func.coalesce(func.sum(expr), 0)), model, tenant_id)
    q = q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)
    return _f(q.scalar())


def _admin_once_per_claim(db, tenant_id, start=None, end=None, claim_ids=None) -> float:
    """ABI administration fee summed ONCE per claim (the latest hire record's
    value), regardless of how many hire vehicles a claim has. The fee is a
    claim-level charge, so summing it per hire record would double-count it."""
    q = (
        db.query(HireDetail.claim_id, HireDetail.abi_administration_fee)
        .join(Claim, HireDetail.claim_id == Claim.id)
        .filter(Claim.is_deleted.isnot(True))
        .filter(HireDetail.abi_administration_fee.isnot(None))
        .distinct(HireDetail.claim_id)
        .order_by(HireDetail.claim_id, HireDetail.created_at.desc())
    )
    if tenant_id is not None:
        q = q.filter(Claim.tenant_id == tenant_id)
    if start and end:
        q = q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)
    if claim_ids is not None:
        if not claim_ids:
            return 0.0
        q = q.filter(HireDetail.claim_id.in_(claim_ids))
    return _f(sum(_f(r[1]) for r in q.all()))


def _hire_income(db, tenant_id, start=None, end=None, claim_ids=None) -> float:
    """Hire income = Σ(ABI rate × the vehicle's final off-hire days). Uses the
    rate×days formula (not the stored total_abi_hire_charge, which bakes in the
    admin fee and would double-count it). On-hire vehicles have no final days, so
    they contribute 0 and are naturally excluded."""
    expr = HireDetail.abi_hire_charge_per_day * func.coalesce(HireDetail.final_total_no_of_hire_days, 0)
    q = _scoped(db.query(func.coalesce(func.sum(expr), 0)), HireDetail, tenant_id)
    if start and end:
        q = q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)
    if claim_ids is not None:
        if not claim_ids:
            return 0.0
        q = q.filter(HireDetail.claim_id.in_(claim_ids))
    return _f(q.scalar())


def _abi_30day_total(db, tenant_id, start=None, end=None, claim_ids=None) -> float:
    """The 0-30 base-ABI 'Total Hire Charge' billed across claims (excl VAT):
    Σ((ABI rate + extra) × off-hire days) + the admin fee once per claim. Mirrors
    the 0-30 section on the ABI & BHR screen."""
    expr = (
        HireDetail.abi_hire_charge_per_day + func.coalesce(HireDetail.abi_extra_charges_per_day, 0)
    ) * func.coalesce(HireDetail.final_total_no_of_hire_days, 0)
    q = _scoped(db.query(func.coalesce(func.sum(expr), 0)), HireDetail, tenant_id)
    if start and end:
        q = q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)
    if claim_ids is not None:
        if not claim_ids:
            return 0.0
        q = q.filter(HireDetail.claim_id.in_(claim_ids))
    hire_extra = _f(q.scalar())
    return round(hire_extra + _admin_once_per_claim(db, tenant_id, start, end, claim_ids), 2)


def _system_calc_excl(db, tenant_id, start=None, end=None, claim_ids=None) -> float:
    """System Calculated Settlement subtotal (Excl. VAT), summed across claims —
    mirrors the Comparison/Hire-Payment 'actual cost': hire (Σ rate×days) + admin
    (once/claim) + storage + recovery + engineer + plating + repair (excl VAT).
    CDW & C&D are BHR-only (0 for the ABI actual)."""
    def _s(model, col):
        if claim_ids is not None:
            return _sum_for_claim_ids(db, model, col, tenant_id, claim_ids)
        if start and end:
            return _sum_in_period(db, model, col, tenant_id, start, end)
        return _sum(db, model, col, tenant_id)

    total = (
        _hire_income(db, tenant_id, start, end, claim_ids)
        + _admin_once_per_claim(db, tenant_id, start, end, claim_ids)
        + _s(Storage, Storage.total_storage_charges)
        + _s(Recovery, Recovery.recovery_charges)
        + _s(EngineerDetail, EngineerDetail.engineer_fee)
        + _s(PlatingAdditionalCharges, PlatingAdditionalCharges.total_plating_cost)
        + _s(RouteRepair, RouteRepair.sub_total)  # excl VAT
    )
    return round(total, 2)


def _pct(curr: float, prev: float) -> dict:
    """Percent change of curr vs prev, with an up/down flag.

    Normalised by the larger of the two so the figure is bounded to ±100%
    (0→9 = 100%, 4→9 = 55.6%, 9→4 = -55.6%), rather than (curr-prev)/prev which
    would report 125% for 4→9.
    """
    denom = max(curr, prev)
    if denom <= 0:
        return {"pct": 0.0, "up": True}
    change = round((curr - prev) / denom * 100, 1)
    return {"pct": abs(change), "up": change >= 0}


def _agreed_settlement_total(db: Session, tenant_id: Optional[int], claim_ids=None,
                             start=None, end=None) -> float:
    """Sum of the agreed settlement totals across claims (the "agreed amount"
    from the Actual-vs-Agreed payment screen). Mirrors the form's agreed total:
    days×rate lines + the flat agreed fees. Optionally scoped to a period by the
    claim's file_opened_at (so it lines up with the period-scoped actual cost)."""
    if claim_ids is not None and not claim_ids:
        return 0.0
    q = db.query(ComparisonSettlement).join(Claim, ComparisonSettlement.claim_id == Claim.id)
    q = q.filter(Claim.is_deleted.isnot(True))
    if tenant_id is not None:
        q = q.filter(Claim.tenant_id == tenant_id)
    if claim_ids is not None:
        q = q.filter(ComparisonSettlement.claim_id.in_(claim_ids))
    if start and end:
        q = q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)

    # Screen 3 stores ONE row per hire vehicle (per-vehicle hire), with the
    # claim-level fees replicated on every row. So sum hire across all rows but
    # count the fees ONCE per claim (otherwise multi-vehicle claims double-count).
    by_claim: dict = {}
    for s in q.all():
        by_claim.setdefault(s.claim_id, []).append(s)

    total = 0.0
    for rows in by_claim.values():
        hire = sum(_f(s.agreed_hire_days) * _f(s.agreed_hire_rate) for s in rows)
        s0 = rows[0]  # claim-level fees are identical across the rows
        fees = (
            _f(s0.agreed_storage_days) * _f(s0.agreed_storage_rate)
            + _f(s0.agreed_cdw_days) * _f(s0.agreed_cdw_rate)
            + _f(s0.agreed_admin)
            + _f(s0.agreed_repair_rate)
            + _f(s0.agreed_recovery_rate)
            + _f(s0.agreed_engineer_rate)
            + _f(s0.agreed_plating_rate)
            + _f(s0.agreed_cd_fee)
            + _f(s0.agreed_additional_fees)
            + _f(s0.agreed_penalties)
        )
        total += hire + fees
    return total


def _settlement_amount_total(db: Session, tenant_id: Optional[int], claim_ids=None,
                             start=None, end=None) -> float:
    """Total settlement amount across claims — the 'Settlement Amount Received'
    from the Direct Hire Payment screen. Scoped either to a specific set of claims
    (e.g. the paid/pending ones) or to a period by the claim's file_opened_at."""
    q = (
        db.query(func.coalesce(func.sum(DirectHirePayment.settlement_amount_received), 0))
        .join(Claim, DirectHirePayment.claim_id == Claim.id)
        .filter(Claim.is_deleted.isnot(True))
    )
    if tenant_id is not None:
        q = q.filter(Claim.tenant_id == tenant_id)
    if claim_ids is not None:
        if not claim_ids:
            return 0.0
        q = q.filter(DirectHirePayment.claim_id.in_(claim_ids))
    if start and end:
        q = q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)
    return _f(q.scalar())


def _utc(dt):
    if not dt:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _add_months(dt, months: int):
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    first = dt.replace(year=year, month=month, day=1)
    next_month = (
        first.replace(year=first.year + 1, month=1)
        if first.month == 12
        else first.replace(month=first.month + 1)
    )
    max_day = (next_month - timedelta(days=1)).day
    return first.replace(day=min(dt.day, max_day))


def _replace_year(dt, year: int):
    try:
        return dt.replace(year=year)
    except ValueError:
        return dt.replace(year=year, day=28)


def _month_label(dt, show_year=False) -> str:
    label = _MONTHS[dt.month - 1]
    return f"{label} {dt.year}" if show_year else label


def _count_between(dates, start, end) -> int:
    return sum(1 for d in dates if d and start <= d < end)


def get_trends(db: Session, tenant_id: Optional[int],
               period: str = "YTD", mode: str = "YoY",
               referrer: Optional[str] = None, status: Optional[str] = None,
               start: Optional[str] = None, end: Optional[str] = None,
               view: Optional[str] = None) -> dict:
    """Claims + hired-vehicle trend series.

    mode=YoY compares the selected period with the same period last year.
    mode=MoM returns month-over-month buckets. Hire trend is a vehicle-count
    trend (hire records), not hire cost. Optionally filtered by referrer
    (source channel) and/or claim status.
    """
    now = datetime.now(timezone.utc)
    claims_q = db.query(Claim).filter(Claim.is_deleted.isnot(True))
    if tenant_id is not None:
        claims_q = claims_q.filter(Claim.tenant_id == tenant_id)
    if referrer:
        claims_q = claims_q.join(Referrer, Referrer.claim_id == Claim.id).filter(
            Referrer.company_name == referrer)
    if status:
        claims_q = claims_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id).filter(
            CaseStatus.label == status)
    claim_dates = [_utc(c.file_opened_at) for c in claims_q.all() if c.file_opened_at]

    hire_q = _scoped(db.query(HireDetail.hire_out, HireDetail.created_at), HireDetail, tenant_id)
    if referrer:
        hire_q = hire_q.join(Referrer, Referrer.claim_id == Claim.id).filter(
            Referrer.company_name == referrer)
    # The Hire Trend's Status filter is the hire status (not a claim status):
    # On Hire = the provided vehicle is in the On Hire status; Off Hire = any
    # other (returned) status. No status ⇒ overall (both vehicles).
    _hire_status = (status or "").strip().lower()
    if _hire_status in ("on hire", "on_hire", "onhire"):
        hire_q = hire_q.join(
            HireVehicleProvided, HireDetail.hire_vehicle_provided_id == HireVehicleProvided.id
        ).filter(HireVehicleProvided.hire_vehicle_status_id == _ON_HIRE_STATUS)
    elif _hire_status in ("off hire", "off_hire", "offhire"):
        hire_q = hire_q.join(
            HireVehicleProvided, HireDetail.hire_vehicle_provided_id == HireVehicleProvided.id
        ).filter(HireVehicleProvided.hire_vehicle_status_id != _ON_HIRE_STATUS)
    elif status:
        # Legacy claim-status filter (only the Claims chart sends these).
        hire_q = hire_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id).filter(
            CaseStatus.label == status)
    hire_rows = hire_q.all()
    hire_dates = [_utc(hire_out or created_at) for hire_out, created_at in hire_rows if hire_out or created_at]

    period = (period or "YTD").upper()
    mode = (mode or "").upper()
    view = (view or "").lower()   # "summary" | "detail" — Claims-only YoY/MoM drill-down

    # Company financial year starts in November (FY Q1 = Nov/Dec/Jan).
    FY_START_MONTH = 11

    def _fy_start(dt):
        """Nov-1 start of the financial year that contains `dt`."""
        yr = dt.year if dt.month >= FY_START_MONTH else dt.year - 1
        return dt.replace(year=yr, month=FY_START_MONTH, day=1,
                          hour=0, minute=0, second=0, microsecond=0)

    def _month_bounds(dt):
        """First instant of dt's month and of the following month."""
        s = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return s, _add_months(s, 1)

    def _month_weeks(dt):
        """7-day buckets across dt's month: 1–7, 8–14, 15–21, 22–28, then the
        leftover days (29–end) as Week 5. A week never holds more than 7 days."""
        s, nxt = _month_bounds(dt)
        weeks = []
        cur = s
        while cur < nxt:
            end = min(cur + timedelta(days=7), nxt)
            weeks.append((cur, end))
            cur = end
        return weeks

    # Legend labels + comparison ranges are only set for two-series views;
    # prev_ranges == None ⇒ a single-series chart (no comparison line).
    current_label = previous_label = None
    prev_ranges = None

    # ── Custom comparison (Claims + Hire trend): compare two user-picked years
    #    month-by-month, or two months week-by-week. start = baseline (grey),
    #    end = current (blue). ──────────────────────────────────────────────
    if period == "CUSTOM" and view == "year" and start and end:
        def _ym(y, m):
            return datetime(y, m, 1, tzinfo=timezone.utc)
        try:
            ya, yb = int(start), int(end)
        except (TypeError, ValueError):
            ya, yb = now.year - 1, now.year
        # Four calendar quarters (Q1 Jan–Mar … Q4 Oct–Dec) of each year.
        labels = ["Q1", "Q2", "Q3", "Q4"]
        cur_ranges = [(_ym(yb, q * 3 + 1), _add_months(_ym(yb, q * 3 + 1), 3)) for q in range(4)]
        prev_ranges = [(_ym(ya, q * 3 + 1), _add_months(_ym(ya, q * 3 + 1), 3)) for q in range(4)]
        current_label, previous_label = str(yb), str(ya)
    elif period == "CUSTOM" and view == "month" and start and end:
        def _pm(s):
            try:
                yy, mm = str(s).split("-")
                return datetime(int(yy), int(mm), 1, tzinfo=timezone.utc)
            except Exception:
                return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        a_dt, b_dt = _pm(start), _pm(end)
        cur_ranges = _month_weeks(b_dt)
        prev_ranges = _month_weeks(a_dt)
        labels = [f"Week {i + 1}" for i in range(max(len(cur_ranges), len(prev_ranges)))]
        current_label = _month_label(b_dt, show_year=True)
        previous_label = _month_label(a_dt, show_year=True)
    # ── Claims-only YoY / MoM drill-down (financial-year aware). `view` is sent
    #    only by the Claims Trend chart, so the Hire Trend keeps its original
    #    period-based behavior. ──────────────────────────────────────────────
    elif view and mode == "YOY":
        cur_fy = _fy_start(now)
        prev_fy = _add_months(cur_fy, -12)
        if view == "detail":
            # Four quarters: this FY vs last FY (Q1 Nov–Jan … Q4 Aug–Oct).
            labels = ["Q1", "Q2", "Q3", "Q4"]
            cur_ranges = [(_add_months(cur_fy, q * 3), _add_months(cur_fy, q * 3 + 3)) for q in range(4)]
            prev_ranges = [(_add_months(prev_fy, q * 3), _add_months(prev_fy, q * 3 + 3)) for q in range(4)]
            # Plain ending-year labels so the legend reads "2026" / "2025"
            # (not "FY 2025/26", which confuses non-finance users).
            current_label = str(cur_fy.year + 1)
            previous_label = str(prev_fy.year + 1)
        else:
            # Summary: two points — total claims last FY vs this FY.
            labels = [str(prev_fy.year + 1), str(cur_fy.year + 1)]
            cur_ranges = [(prev_fy, _add_months(prev_fy, 12)), (cur_fy, _add_months(cur_fy, 12))]
    elif view and mode == "MOM":
        if view == "detail":
            # Weekly buckets (7 days each, week 5 for leftover days): current vs previous month.
            cur_ranges = _month_weeks(now)
            prev_ranges = _month_weeks(_add_months(now, -1))
            labels = [f"Week {i + 1}" for i in range(max(len(cur_ranges), len(prev_ranges)))]
            current_label = _month_label(now)
            previous_label = _month_label(_add_months(now, -1))
        else:
            # Summary: two points — total claims previous month vs current month.
            prev_s, prev_e = _month_bounds(_add_months(now, -1))
            cur_s, cur_e = _month_bounds(now)
            labels = [_month_label(_add_months(now, -1)), _month_label(now)]
            cur_ranges = [(prev_s, prev_e), (cur_s, cur_e)]
    # ── Original period-based buckets (Hire Trend + Claims WTD/MTD/YTD) ───────
    elif period == "WTD":
        monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        # Working week only — Sat/Sun are non-working days, excluded from WTD.
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        cur_ranges = [(monday + timedelta(days=i), monday + timedelta(days=i + 1)) for i in range(5)]
    elif period == "MTD":
        # Weekly buckets (Week 1, Week 2, …) across the WHOLE month so the chart
        # always shows a full line — even in the first week of the month, the
        # later weeks are still plotted (they read 0 until those days arrive).
        first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = _add_months(first, 1)  # first day of next month
        labels, cur_ranges = [], []
        wk, s = 1, first
        while s < month_end:
            e = min(s + timedelta(days=7), month_end)
            labels.append(f"Week {wk}")
            cur_ranges.append((s, e))
            s += timedelta(days=7)
            wk += 1
    elif period == "CUSTOM" and start and end:
        # Custom range: daily buckets for short spans (≤45 days), monthly otherwise.
        try:
            s_dt = datetime.fromisoformat(start).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            e_dt = datetime.fromisoformat(end).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc) + timedelta(days=1)
        except Exception:
            s_dt = e_dt = None
        labels, cur_ranges = [], []
        if s_dt and e_dt and e_dt > s_dt:
            if (e_dt - s_dt).days <= 45:
                d = s_dt
                while d < e_dt:
                    labels.append(f"{d.day} {_MONTHS[d.month - 1]}")
                    cur_ranges.append((d, d + timedelta(days=1)))
                    d += timedelta(days=1)
            else:
                m = s_dt.replace(day=1)
                while m < e_dt:
                    nxt = _add_months(m, 1)
                    labels.append(_month_label(m, show_year=True))
                    cur_ranges.append((m, min(nxt, e_dt)))
                    m = nxt
    else:  # YTD → 12 months
        labels = list(_MONTHS)
        cur_ranges = []
        for m in range(1, 13):
            s = now.replace(month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
            e = s.replace(year=s.year + 1, month=1) if m == 12 else s.replace(month=m + 1)
            cur_ranges.append((s, e))

    # On the original period-based path a YoY/MoM mode still adds a shifted
    # comparison series (used by the Hire Trend's own toggle). The drill-down
    # views (view != "") manage prev_ranges themselves — a summary view stays
    # single-series — so skip them here.
    if prev_ranges is None and not view and mode in ("YOY", "MOM"):
        def _shift(dt):
            return _add_months(dt, -1) if mode == "MOM" else _add_months(dt, -12)
        prev_ranges = [(_shift(s), _shift(e)) for s, e in cur_ranges]
        if mode == "MOM":
            current_label = _month_label(now, show_year=True)
            previous_label = _month_label(_add_months(now, -1), show_year=True)
        else:
            current_label = str(now.year)
            previous_label = str(now.year - 1)

    def _range_label(s, e):
        """Human-readable span for a bucket, e.g. 'Nov 2024–Jan 2025' or 'Jun 2026'."""
        last = e - timedelta(days=1)
        a = f"{_MONTHS[s.month - 1]} {s.year}"
        b = f"{_MONTHS[last.month - 1]} {last.year}"
        return a if a == b else f"{a}–{b}"

    def _series(dates, ranges):
        return [{"label": labels[i], "value": _count_between(dates, s, e), "range": _range_label(s, e)}
                for i, (s, e) in enumerate(ranges)]

    def _prev(dates):
        return _series(dates, prev_ranges) if prev_ranges else []

    return {
        "claims_trend": _series(claim_dates, cur_ranges),
        "claims_trend_prev": _prev(claim_dates),
        "hire_trend": _series(hire_dates, cur_ranges),
        "hire_trend_prev": _prev(hire_dates),
        "series_labels": {
            "current": current_label or str(now.year),
            "previous": previous_label or str(now.year - 1),
        },
    }


def get_trend_options(db: Session, tenant_id: Optional[int]) -> dict:
    """Referrer + status options for the trend filters. Referrers are the distinct
    company names recorded on the Referrer Details screen across the tenant's
    claims (every referrer chosen for any claim). Statuses = all active case
    statuses."""
    ref_q = (
        db.query(Referrer.company_name)
        .join(Claim, Referrer.claim_id == Claim.id)
        .filter(Claim.is_deleted.isnot(True), Referrer.company_name.isnot(None))
    )
    if tenant_id is not None:
        ref_q = ref_q.filter(Claim.tenant_id == tenant_id)
    referrers = sorted({r[0].strip() for r in ref_q.distinct().all() if r[0] and r[0].strip()})
    statuses = [r[0] for r in (
        db.query(CaseStatus.label)
        .filter(CaseStatus.is_active == True)  # noqa: E712
        .order_by(CaseStatus.sort_order, CaseStatus.label)
        .all()
    ) if r[0]]
    return {"referrers": referrers, "statuses": statuses}


def _period_bounds(period: str, start: Optional[str], end: Optional[str], now):
    """[start, end) datetimes for a period; (None, None) = all-time."""
    period = (period or "").upper()
    if period == "WTD":
        s = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        # Mon–Fri only (Sat/Sun excluded as non-working days).
        return s, s + timedelta(days=5)
    if period == "MTD":
        s = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        e = s.replace(year=s.year + 1, month=1) if s.month == 12 else s.replace(month=s.month + 1)
        return s, e
    if period == "YTD":
        s = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return s, s.replace(year=s.year + 1)
    if period == "CUSTOM" and start and end:
        try:
            s = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
            e = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)
            return s, e
        except Exception:
            return None, None
    return None, None


def get_income(db: Session, tenant_id: Optional[int], period: str = "ALL",
               start: Optional[str] = None, end: Optional[str] = None) -> dict:
    """Net income breakdown for a period (WTD/MTD/YTD/CUSTOM), by claim open date."""
    now = datetime.now(timezone.utc)
    s, e = _period_bounds(period, start, end, now)
    if s and e:
        hire = _hire_income(db, tenant_id, s, e)
        admin = _admin_once_per_claim(db, tenant_id, s, e)
        storage = _sum_in_period(db, Storage, Storage.total_storage_charges, tenant_id, s, e)
        engineer = _sum_in_period(db, EngineerDetail, EngineerDetail.engineer_fee, tenant_id, s, e)
        recovery = _sum_in_period(db, Recovery, Recovery.recovery_charges, tenant_id, s, e)
    else:
        hire = _hire_income(db, tenant_id)
        admin = _admin_once_per_claim(db, tenant_id)
        storage = _sum(db, Storage, Storage.total_storage_charges, tenant_id)
        engineer = _sum(db, EngineerDetail, EngineerDetail.engineer_fee, tenant_id)
        recovery = _sum(db, Recovery, Recovery.recovery_charges, tenant_id)
    total = hire + storage + recovery + admin + engineer
    return {
        "hire": round(hire, 2), "storage": round(storage, 2), "recovery": round(recovery, 2),
        "admin": round(admin, 2), "engineer": round(engineer, 2), "total": round(total, 2),
    }


def get_collection_performance(db: Session, tenant_id: Optional[int],
                               period: str = "YTD",
                               payment_status: Optional[str] = None) -> dict:
    """Collection Performance card, filtered by payment period and status."""
    now = datetime.now(timezone.utc)
    normalized_period = (period or "YTD").upper().replace(" ", "_")
    if normalized_period == "ALL_TIME":
        normalized_period = "ALL"

    s, e = _period_bounds(normalized_period, None, None, now)
    payments_q = _scoped(db.query(HirePaymentDetails), HirePaymentDetails, tenant_id)
    if s and e:
        payments_q = payments_q.filter(
            HirePaymentDetails.created_at >= s,
            HirePaymentDetails.created_at < e,
        )

    status = (payment_status or "").strip().lower()
    if status == "paid":
        payments_q = payments_q.filter(
            func.coalesce(HirePaymentDetails.payments_received_total, 0) > 0,
            func.coalesce(HirePaymentDetails.payment_outstanding_incl_vat, 0) <= 0,
        )
    elif status == "pending":
        payments_q = payments_q.filter(
            func.coalesce(HirePaymentDetails.payment_outstanding_incl_vat, 0) > 0,
        )
    else:
        status = "all"

    received = _f(
        payments_q.with_entities(
            func.coalesce(func.sum(HirePaymentDetails.payments_received_total), 0),
        ).scalar()
    )
    outstanding = _f(
        payments_q.with_entities(
            func.coalesce(func.sum(HirePaymentDetails.payment_outstanding_incl_vat), 0),
        ).scalar()
    )
    claim_ids = [
        claim_id for (claim_id,) in
        payments_q.with_entities(HirePaymentDetails.claim_id).distinct().all()
    ]

    # Actual Amount = the full billed total (System Calculated Settlement excl VAT).
    # Agreed Amount = the settled/paid portion; the Pending filter shows the rest
    # of the billed total still outstanding (billed − settled), so Paid + Pending
    # add up to the billed total instead of Pending being £0.
    settled = _settlement_amount_total(db, tenant_id, start=s, end=e)
    system_billed = _system_calc_excl(db, tenant_id, s, e)
    if status == "pending":
        agreed_settlement = max(0.0, round(system_billed - settled, 2))
    else:  # "paid" or no filter → the settled amount
        agreed_settlement = settled

    denom = received + outstanding
    collection_pct = round((received / denom) * 100) if denom else 0

    return {
        "collected": round(received, 2),
        "outstanding": round(outstanding, 2),
        "pct": collection_pct,
        "actual_collection": round(agreed_settlement, 2),
        "billed": round(system_billed, 2),
        "rate": round(agreed_settlement / system_billed * 100) if system_billed else 0,
        "payment_status": status,
        "period": normalized_period,
    }


# (date_field, file_url_field, display label) for the driver-document checklist.
_DOC_FIELDS = [
    ("driver_license_received_on", "driver_license_file_url", "Driving Licence Received On"),
    ("license_checks_completed_on", "license_checks_completed_file_url", "Driving Licence Checks Completed On"),
    ("proof_of_address_1_received_on", "proof_of_address_1_file_url", "Proof of Address 1 Received On"),
    ("proof_of_address_2_received_on", "proof_of_address_2_file_url", "Proof of Address 2 Received On"),
    ("pre_hire_bank_statement_received_on", "pre_hire_bank_statement_file_url", "Bank Statement Received On (Pre-Hire)"),
    ("post_hire_bank_statement_received_on", "post_hire_bank_statement_file_url", "Bank Statement Received On (Post-Hire)"),
    ("taxi_badge_received_on", "taxi_badge_file_url", "Taxi Badge Received On"),
    ("v5_received_on", "v5_file_url", "V5 Received On"),  # counted once (single field)
    ("mot_certificate_received_on", "mot_certificate_file_url", "MOT Certificate Received On"),
    ("insurance_certificate_received_on", "insurance_certificate_file_url", "Insurance Certificate Received On"),
    ("suspension_notice_received_on", "suspension_notice_file_url", "Suspension Notice Received On"),
    ("suspension_uplift_received_on", "suspension_uplift_file_url", "Suspension UPLIFT Received On"),
    ("signed_cha_received_on", "signed_cha_file_url", "Signed CHA Received On"),
    ("signed_mitigation_received_on", "signed_mitigation_file_url", "Signed Mitigation Received On"),
    ("arf_received_on", "arf_file_url", "ARF Received On"),
    ("signed_cil_agreement_received_on", "signed_cil_agreement_file_url", "Signed CIL Agreement Received On"),
]


def get_missing_documents(db: Session, tenant_id: Optional[int]) -> dict:
    """Every required document that's missing, per claim. A doc is present if its
    received-date OR file-url is set (V5 is one field, so counted once). The
    engineer report is tracked separately via EngineerDetail."""
    from libdata.models.tables import DriverDocumentAgreement
    from appflow.utils import build_case_reference

    claims_q = db.query(Claim).filter(Claim.is_deleted.isnot(True))
    if tenant_id is not None:
        claims_q = claims_q.filter(Claim.tenant_id == tenant_id)

    items = []
    for c in claims_q.all():
        try:
            ref = build_case_reference(c.id, db)
        except Exception:
            ref = str(c.id)
        agr = db.query(DriverDocumentAgreement).filter(DriverDocumentAgreement.claim_id == c.id).first()
        for date_f, url_f, label in _DOC_FIELDS:
            present = agr and (getattr(agr, date_f, None) or getattr(agr, url_f, None))
            if not present:
                items.append({"label": label, "claim_id": c.id, "claim_reference": ref})
        eng = db.query(EngineerDetail).filter(EngineerDetail.claim_id == c.id).first()
        if not (eng and eng.engineer_report_received):
            items.append({"label": "Engineer Report Received On", "claim_id": c.id, "claim_reference": ref})

    return {"total": len(items), "items": items}


def get_storage_recovery(db: Session, tenant_id: Optional[int]) -> dict:
    """Storage & Recovery summary + per-vehicle breakdown for the dashboard
    sliders. Each item carries the claim's vehicle (reg + make/model), the fee
    and the case reference."""
    from appflow.utils import build_case_reference

    def _veh(claim_id):
        v = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
        reg = (v.registration if v else None) or "—"
        make_model = " ".join(p for p in [(v.make if v else None), (v.model if v else None)] if p) if v else ""
        return reg, make_model

    def _build(model, fee_attr):
        q = db.query(model).join(Claim, model.claim_id == Claim.id).filter(Claim.is_deleted.isnot(True))
        if tenant_id is not None:
            q = q.filter(Claim.tenant_id == tenant_id)
        items, total = [], 0.0
        for rec in q.all():
            fee = _f(getattr(rec, fee_attr, None))
            total += fee
            reg, make_model = _veh(rec.claim_id)
            try:
                ref = build_case_reference(rec.claim_id, db)
            except Exception:
                ref = str(rec.claim_id)
            items.append({
                "claim_id": rec.claim_id,
                "registration": reg,
                "make_model": make_model,
                "fee": round(fee, 2),
                "claim_reference": ref,
            })
        return {"count": len(items), "total": round(total, 2), "items": items}

    return {
        "storage": _build(Storage, "total_storage_charges"),
        "recovery": _build(Recovery, "recovery_charges"),
    }


def get_dashboard(db: Session, tenant_id: Optional[int],
                  period: str = "ALL", start: Optional[str] = None,
                  end: Optional[str] = None, current_user: Optional[int] = None) -> dict:
    _ = (period, start, end)
    now = datetime.now(timezone.utc)

    claims_q = db.query(Claim).filter(Claim.is_deleted.isnot(True))
    if tenant_id is not None:
        claims_q = claims_q.filter(Claim.tenant_id == tenant_id)
    claims_reported = claims_q.count()

    # Vehicles on hire = hire-provided vehicles currently in the "On Hire" status
    # (not the claimant's own client vehicles).
    veh_q = _scoped(db.query(func.count(HireVehicleProvided.id)), HireVehicleProvided, tenant_id).filter(
        HireVehicleProvided.hire_vehicle_status_id == _ON_HIRE_STATUS,
        HireVehicleProvided.is_deleted == False,  # noqa: E712
    )
    vehicles = int(veh_q.scalar() or 0)

    # ── financials ────────────────────────────────────────────────────────────
    received = _sum(db, HirePaymentDetails, HirePaymentDetails.payments_received_total, tenant_id)
    outstanding = _sum(db, HirePaymentDetails, HirePaymentDetails.payment_outstanding_incl_vat, tenant_id)

    # Income comes from the MVP detail tables (what the user actually fills in),
    # not the payment-pack tables (which may be empty). These stay all-time —
    # the net-income breakdown, storage/recovery and collection cards have their
    # own period semantics, so the global filter must not double-filter them.
    hire = _hire_income(db, tenant_id)
    admin = _admin_once_per_claim(db, tenant_id)  # once per claim (not per hire vehicle)
    storage = _sum(db, Storage, Storage.total_storage_charges, tenant_id)
    engineer = _sum(db, EngineerDetail, EngineerDetail.engineer_fee, tenant_id)
    recovery = _sum(db, Recovery, Recovery.recovery_charges, tenant_id)
    net_income = hire + storage + recovery + admin + engineer

    # Agreed settlement total (for Collection Performance "Actual Collection").
    agreed_settlement = _agreed_settlement_total(db, tenant_id)

    # outstanding debtor count = claims that still owe
    debtors_count = _scoped(
        db.query(func.count(func.distinct(HirePaymentDetails.claim_id))),
        HirePaymentDetails, tenant_id,
    ).filter(HirePaymentDetails.payment_outstanding_incl_vat > 0).scalar() or 0

    # collection performance YTD
    denom = received + outstanding
    collection_pct = round((received / denom) * 100) if denom else 0

    # ── debtors age = settlement aging ────────────────────────────────────────
    # Each claim's settlement amount (Direct Hire Payment screen) is bucketed by
    # the days between payment-pack generation (ABIBHRCharges.payment_pack_raised_date)
    # and the settlement date (DirectHirePayment.date_settlement_received).
    # Claims without both dates can't be aged, so they're skipped.
    buckets = {"0-30 Days": 0.0, "31-60 Days": 0.0, "61-90 Days": 0.0, "90+ Days": 0.0}
    settle_q = db.query(
        DirectHirePayment.claim_id,
        DirectHirePayment.settlement_amount_received,
        DirectHirePayment.date_settlement_received,
    ).join(Claim, DirectHirePayment.claim_id == Claim.id).filter(Claim.is_deleted.isnot(True))
    if tenant_id is not None:
        settle_q = settle_q.filter(Claim.tenant_id == tenant_id)
    settle_rows = settle_q.all()

    # Batch-load the payment-pack raised date per claim in ONE query. This used to
    # be an N+1 (a separate ABIBHRCharges lookup for every settlement row), which
    # was the dashboard's main slowdown against the remote DB.
    settle_claim_ids = {r[0] for r in settle_rows if r[0] is not None}
    raised_by_claim = {}
    if settle_claim_ids:
        for cid, raised in (
            db.query(ABIBHRCharges.claim_id, ABIBHRCharges.payment_pack_raised_date)
            .filter(ABIBHRCharges.claim_id.in_(settle_claim_ids),
                    ABIBHRCharges.payment_pack_raised_date.isnot(None))
            .all()
        ):
            # Keep the first non-null per claim (matches the old .first() semantics).
            if cid not in raised_by_claim:
                raised_by_claim[cid] = raised

    for claim_id_val, settlement_amount, date_settled in settle_rows:
        amount = _f(settlement_amount)
        if amount <= 0 or not date_settled:
            continue
        raised = raised_by_claim.get(claim_id_val)
        if not raised:
            continue  # no payment-pack date → can't compute the age
        days = max(0, (date_settled - raised).days)
        # Non-overlapping bands: 0-30, 31-60, 61-90, 90+ (a day-30 claim is only in 0-30).
        key = "0-30 Days" if days <= 30 else "31-60 Days" if days <= 60 else "61-90 Days" if days <= 90 else "90+ Days"
        buckets[key] += amount
    debtors_age = [{"label": k, "amount": round(v, 2)} for k, v in buckets.items()]

    # ── trends (default YTD; the charts re-fetch per period via /dashboard/trends)
    _trends = get_trends(db, tenant_id, "YTD")
    claims_trend = _trends["claims_trend"]
    hire_trend = _trends["hire_trend"]

    # ── counts / attention (proxies noted) ────────────────────────────────────
    today = now.date()

    # Urgent alerts counts the logged-in user's overdue tasks — past their due date
    # and not finished (same definition as Task Management's "Overdue" box) — scoped
    # to them by assigned_user (email handle, normalised). User-scoping already keeps
    # out other people's past-due tasks.
    urgent_tasks_q = db.query(func.count(Task.id)).filter(
        Task.is_deleted == False,
        Task.due_date.isnot(None),
        Task.due_date < today,
        Task.status.notin_(_TERMINAL),
    )
    if tenant_id is not None:
        urgent_tasks_q = urgent_tasks_q.filter(Task.tenant_id == tenant_id)
    if current_user is not None:
        me = db.query(User).filter(User.id == current_user).first()
        handle = (me.user_name.split("@")[0] if me and me.user_name else "")
        norm_me = re.sub(r"[^a-z0-9]", "", handle.lower())
        norm_assignee = func.regexp_replace(
            func.lower(func.coalesce(Task.assigned_user, "")), "[^a-z0-9]", "", "g"
        )
        urgent_tasks_q = urgent_tasks_q.filter(norm_assignee == norm_me)
    overdue_tasks = int(urgent_tasks_q.scalar() or 0)

    # Attention-required claims = those whose case status is "Pending".
    overdue_claims = (
        claims_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id)
        .filter(func.lower(CaseStatus.label) == "pending")
        .count()
    )

    # Urgent alerts = (your) Overdue-status tasks + attention-required (Pending) claims.
    urgent_alerts = overdue_tasks + int(overdue_claims)
    # Real missing-document count (driver-document checklist + engineer report).
    missing_documents = get_missing_documents(db, tenant_id)["total"]

    # ── operational insights ──────────────────────────────────────────────────
    approved_claims = (
        claims_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id)
        .filter(func.lower(CaseStatus.label).in_(("accepted", "completed")))
        .count()
    )
    # Avg resolution time: days from file open to last update, over resolved claims.
    resolved = (
        claims_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id)
        .filter(func.lower(CaseStatus.label).in_(("accepted", "completed", "rejected", "cancelled")))
        .filter(Claim.file_opened_at.isnot(None))
        .all()
    )
    _res_days = [(c.updated_at - c.file_opened_at).days for c in resolved
                 if c.updated_at and c.file_opened_at]
    avg_resolution_days = round(sum(_res_days) / len(_res_days)) if _res_days else 0

    # Today's activity for the Daily Operational Insights panel.
    _today_s = now.replace(hour=0, minute=0, second=0, microsecond=0)
    _today_e = _today_s + timedelta(days=1)
    claims_created_today = claims_q.filter(
        Claim.file_opened_at >= _today_s, Claim.file_opened_at < _today_e
    ).count()
    approved_claims_today = (
        claims_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id)
        .filter(func.lower(CaseStatus.label).in_(("accepted", "completed")))
        .filter(Claim.updated_at >= _today_s, Claim.updated_at < _today_e)
        .count()
    )
    vehicle_hires_today = int(
        _scoped(db.query(func.count(HireDetail.id)), HireDetail, tenant_id)
        .filter(HireDetail.hire_out >= _today_s, HireDetail.hire_out < _today_e)
        .scalar() or 0
    )

    # Storage / Recovery vehicle counts (for the "N Vehicles" line on the card).
    def _sr_count(model):
        q = _scoped(db.query(func.count(model.id)), model, tenant_id)
        return int(q.scalar() or 0)
    _sr_counts = {"storage": _sr_count(Storage), "recovery": _sr_count(Recovery)}

    # ── month-over-month trend % for the cards (this month vs last month) ──────
    this_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_start = (this_start.replace(year=this_start.year - 1, month=12)
                  if this_start.month == 1 else this_start.replace(month=this_start.month - 1))
    next_start = (this_start.replace(year=this_start.year + 1, month=1)
                  if this_start.month == 12 else this_start.replace(month=this_start.month + 1))

    def _income_period(start, end):
        return (
            _hire_income(db, tenant_id, start, end)
            + _admin_once_per_claim(db, tenant_id, start, end)
            + _sum_in_period(db, Storage, Storage.total_storage_charges, tenant_id, start, end)
            + _sum_in_period(db, EngineerDetail, EngineerDetail.engineer_fee, tenant_id, start, end)
            + _sum_in_period(db, Recovery, Recovery.recovery_charges, tenant_id, start, end)
        )

    def _claims_period(start, end):
        return claims_q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end).count()

    def _vehicles_period(start, end):
        q = _scoped(db.query(func.count(HireVehicleProvided.id)), HireVehicleProvided, tenant_id).filter(
            HireVehicleProvided.hire_vehicle_status_id == _ON_HIRE_STATUS,
            HireVehicleProvided.is_deleted == False,  # noqa: E712
        )
        return int(q.filter(Claim.file_opened_at >= start, Claim.file_opened_at < end).scalar() or 0)

    def _urgent_period(start, end):
        # Same two ingredients as the live urgent-alerts count — (your) unfinished
        # past-due tasks + Pending claims — but each bounded to the period by its
        # own date, so this-month vs last-month gives a directional MoM trend.
        s_date, e_date = start.date(), end.date()
        tq = db.query(func.count(Task.id)).filter(
            Task.is_deleted == False,  # noqa: E712
            Task.due_date.isnot(None),
            Task.due_date >= s_date,
            Task.due_date < e_date,
            Task.due_date < today,
            Task.status.notin_(_TERMINAL),
        )
        if tenant_id is not None:
            tq = tq.filter(Task.tenant_id == tenant_id)
        if current_user is not None:
            _me = db.query(User).filter(User.id == current_user).first()
            _handle = (_me.user_name.split("@")[0] if _me and _me.user_name else "")
            _norm_me = re.sub(r"[^a-z0-9]", "", _handle.lower())
            _norm_assignee = func.regexp_replace(
                func.lower(func.coalesce(Task.assigned_user, "")), "[^a-z0-9]", "", "g"
            )
            tq = tq.filter(_norm_assignee == _norm_me)
        tasks_ct = int(tq.scalar() or 0)
        claims_ct = (
            claims_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id)
            .filter(func.lower(CaseStatus.label) == "pending")
            .filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)
            .count()
        )
        return tasks_ct + claims_ct

    def _claims_status_period(start, end, keywords):
        # Claims opened in the period whose case-status label matches any keyword
        # (mirrors the Claims list's status buckets).
        conds = [func.lower(CaseStatus.label).like(f"%{k}%") for k in keywords]
        return (
            claims_q.join(CaseStatus, Claim.case_status_id == CaseStatus.id)
            .filter(Claim.file_opened_at >= start, Claim.file_opened_at < end)
            .filter(or_(*conds))
            .count()
        )

    trends = {
        "net_income": _pct(_income_period(this_start, next_start), _income_period(last_start, this_start)),
        "claims_reported": _pct(_claims_period(this_start, next_start), _claims_period(last_start, this_start)),
        # Per-status MoM trends for the Claims list's Pending / Processing / Approved cards.
        "claims_pending": _pct(
            _claims_status_period(this_start, next_start, ["pending"]),
            _claims_status_period(last_start, this_start, ["pending"]),
        ),
        "claims_processing": _pct(
            _claims_status_period(this_start, next_start, ["process", "tbc", "progress"]),
            _claims_status_period(last_start, this_start, ["process", "tbc", "progress"]),
        ),
        "claims_approved": _pct(
            _claims_status_period(this_start, next_start, ["approve", "accept", "complete"]),
            _claims_status_period(last_start, this_start, ["approve", "accept", "complete"]),
        ),
        "vehicles": _pct(_vehicles_period(this_start, next_start), _vehicles_period(last_start, this_start)),
        "urgent_alerts": _pct(_urgent_period(this_start, next_start), _urgent_period(last_start, this_start)),
        # Outstanding Debtors card = System-Calculated Settlement (excl VAT); trend
        # compares this month's billed total vs last month's.
        "outstanding_debtors_billed": _pct(
            _system_calc_excl(db, tenant_id, this_start, next_start),
            _system_calc_excl(db, tenant_id, last_start, this_start),
        ),
    }

    # The top KPI cards honour the dashboard's own period filter (WTD/MTD/YTD or
    # a CUSTOM range) — scoped by claim file_opened_at via the same helpers used
    # for the MoM trend. Live snapshot metrics (Vehicles on hire, Fleet
    # Availability, Urgent Alerts) have no period semantics and stay as-is.
    _ps, _pe = _period_bounds(period, start, end, now)
    if _ps and _pe:
        _claims_reported_card = _claims_period(_ps, _pe)
        _net_income_card = round(_income_period(_ps, _pe), 2)
        _debtors_billed_card = _system_calc_excl(db, tenant_id, _ps, _pe)
    else:
        _claims_reported_card = claims_reported
        _net_income_card = round(net_income, 2)
        _debtors_billed_card = _system_calc_excl(db, tenant_id)

    return {
        "trends": trends,
        "stats": {
            "claims_reported": _claims_reported_card,
            "vehicles": vehicles,
            "outstanding_debtors_count": int(debtors_count),
            "outstanding_debtors_amount": round(outstanding, 2),
            # System Calculated Settlement subtotal (excl VAT) across claims — shown
            # on the Outstanding Debtors card.
            "outstanding_debtors_billed": _debtors_billed_card,
            "net_income": _net_income_card,
            "availability_pct": 78,  # fleet metric — static until Fleet is built
            "urgent_alerts": urgent_alerts,
            "approved_claims": approved_claims,
            "avg_resolution_days": avg_resolution_days,
            # Today-only metrics for the Daily Operational Insights panel.
            "claims_created_today": claims_created_today,
            "approved_claims_today": approved_claims_today,
            "vehicle_hires_today": vehicle_hires_today,
        },
        "attention": {
            "overdue_claims": overdue_claims,
            "missing_documents": missing_documents,
            "vehicles_overdue_return": 0,  # fleet — static
        },
        "net_income_breakdown": {
            "hire": round(hire, 2),
            "storage": round(storage, 2),
            "recovery": round(recovery, 2),
            "admin": round(admin, 2),
            "engineer": round(engineer, 2),
            "total": round(net_income, 2),
        },
        "debtors_age": debtors_age,
        # Total shown next to the heading = the exclusive-of-VAT outstanding
        # amount from the Hire Payment Details screen (payment screen 4).
        "debtors_total": round(
            _sum(db, HirePaymentDetails, HirePaymentDetails.payment_outstanding_excl_vat, tenant_id), 2
        ),
        "collection_ytd": {
            "collected": round(received, 2),
            "outstanding": round(outstanding, 2),
            "pct": collection_pct,
            # Actual Collection = agreed settlement total; Actual Amount (billed) =
            # the System Calculated Settlement excl VAT (screen 4). Rate = agreed/actual.
            "actual_collection": round(agreed_settlement, 2),
            "billed": _system_calc_excl(db, tenant_id),
            "rate": round(agreed_settlement / _system_calc_excl(db, tenant_id) * 100)
                    if _system_calc_excl(db, tenant_id) else 0,
        },
        "storage_recovery": {
            "storage": {"total": round(storage, 2), "count": _sr_counts["storage"]},
            "recovery": {"total": round(recovery, 2), "count": _sr_counts["recovery"]},
        },
        "claims_trend": claims_trend,
        "hire_trend": hire_trend,
    }
