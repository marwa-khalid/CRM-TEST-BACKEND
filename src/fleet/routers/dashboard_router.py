"""Fleet dashboard endpoints (currently: Hire Trend)."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.services import dashboard_service

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
    return dashboard_service.get_hire_trend(
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
    makes the Urgent Alerts card side-aware."""
    return dashboard_service.get_stats(db, tenant_id, period=period, module=module or None)


@router.get("/dashboard/vehicle-status")
def vehicle_status_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Vehicle-status distribution for the donut."""
    return dashboard_service.get_vehicle_status(db, tenant_id)


@router.get("/dashboard/vehicles")
def fleet_vehicles_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Live vehicle list for the "Skyline Vehicles" section (status + hire info)."""
    return dashboard_service.get_fleet_vehicles(db, tenant_id)


@router.get("/dashboard/weekly-payments")
def weekly_payments_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Cross-hire weekly payment schedule (Due Today / This Week / Overdue / Received Today)."""
    return dashboard_service.get_weekly_payments(db, tenant_id)


@router.get("/dashboard/compliance")
def compliance_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Per-category compliance summary (MOT / Plate / Road Fund / Service)."""
    return dashboard_service.get_compliance(db, tenant_id)


@router.get("/dashboard/expiries")
def expiries_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Expiry cards (Road Fund / MOT / Plate): tab counts + soonest rows."""
    return dashboard_service.get_expiries(db, tenant_id)


@router.get("/dashboard/attention")
def attention_route(
    side: str = "vehicles",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Attention-required tiles. ``side`` (skyline | vehicles) picks driver-doc vs
    vehicle-doc counting for the Missing Documents tile."""
    return dashboard_service.get_attention(db, tenant_id, side=side)


@router.get("/dashboard/missing-documents")
def missing_documents_route(
    side: str = "vehicles",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Missing documents for the Attention slider. ``side``: skyline → driver docs
    (driving licence / taxi badge); vehicles → vehicle docs (MOT / Plate)."""
    return dashboard_service.get_missing_documents(db, tenant_id, side=side)


@router.get("/dashboard/overdue-returns")
def overdue_returns_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Detail rows for the Overdue Returns slider (vehicles out past return date)."""
    return dashboard_service.get_overdue_returns(db, tenant_id)


@router.get("/dashboard/overdue-payments")
def overdue_payments_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Detail rows for the Overdue Payments slider (owed payments past due date)."""
    return dashboard_service.get_overdue_payments(db, tenant_id)
