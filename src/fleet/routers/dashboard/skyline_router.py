"""Skyline (fleet hire) dashboard endpoints: Hire Trend, top stats, Weekly Payment,
Attention Required (+ its detail sliders). Shared stats/weekly-payment logic lives in
the dashboard `common` service; the rest in `skyline`."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.services.dashboard import common as common_svc
from fleet.services.dashboard import skyline as skyline_svc

router = APIRouter()


@router.get("/dashboard/hire-trend")
def hire_trend_route(
    period: str = "WTD",
    mode: str = "",
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    cmp_type: str = "",
    a: str = "",
    b: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Vehicle-hire counts for the Fleet dashboard's Hire Trend chart.

    ``period``: WTD | MTD | YTD | CUSTOM. ``mode``: YOY | MOM (two-bar compare).
    ``status``: on_hire | off_hire (optional filter). For a Custom year/month
    comparison pass ``cmp_type`` (year|month) with ``a`` and ``b`` (the two periods).
    """
    return skyline_svc.get_hire_trend(
        db, tenant_id, period=period, mode=mode, start=start, end=end,
        status=status, cmp_type=cmp_type, a=a, b=b,
    )


@router.get("/dashboard/stats")
def stats_route(
    period: str = "MTD",
    module: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """The four top stat cards (period: WTD | MTD | YTD). `module` (skyline / vehicles)
    makes the Urgent Alerts card side-aware. Shared by Skyline + VM dashboards."""
    return common_svc.get_stats(db, tenant_id, period=period, module=module or None)


@router.get("/dashboard/weekly-payments")
def weekly_payments_route(
    today: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Cross-hire weekly payment schedule (Due Today / This Week / Overdue / Received).
    ``today`` (YYYY-MM-DD) is the viewer's local date, so the buckets follow whoever's looking."""
    return common_svc.get_weekly_payments(db, tenant_id, client_today=today or None)


@router.get("/dashboard/attention")
def attention_route(
    side: str = "vehicles",
    context: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Attention-required tiles. ``side`` (skyline | vehicles) picks driver-doc vs
    vehicle-doc counting for the Missing Documents tile; ``context`` (cams | skyline)
    scopes the vehicle-doc count to one Vehicle Management side."""
    return skyline_svc.get_attention(db, tenant_id, side=side, context=context or None)


@router.get("/dashboard/missing-documents")
def missing_documents_route(
    side: str = "vehicles",
    context: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Missing documents for the Attention slider. ``side``: skyline → driver docs
    (driving licence / taxi badge); vehicles → vehicle docs (MOT / Plate). ``context``
    (cams | skyline) scopes vehicle docs to one Vehicle Management side."""
    return skyline_svc.get_missing_documents(db, tenant_id, side=side, context=context or None)


@router.get("/dashboard/overdue-returns")
def overdue_returns_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Detail rows for the Overdue Returns slider (vehicles out past return date)."""
    return skyline_svc.get_overdue_returns(db, tenant_id)


@router.get("/dashboard/overdue-payments")
def overdue_payments_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Detail rows for the Overdue Payments slider (owed payments past due date)."""
    return skyline_svc.get_overdue_payments(db, tenant_id)
