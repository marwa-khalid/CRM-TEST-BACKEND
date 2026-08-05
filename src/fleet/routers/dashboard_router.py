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
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Vehicle-hire counts for the Fleet dashboard's Hire Trend chart.

    ``period``: WTD | MTD | YTD | CUSTOM. ``mode``: YOY | MOM (two-bar compare).
    ``status``: on_hire | off_hire (optional filter).
    """
    return dashboard_service.get_hire_trend(db, tenant_id, period=period, mode=mode, start=start, end=end, status=status)


@router.get("/dashboard/stats")
def stats_route(
    period: str = "MTD",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """The four top stat cards (period: WTD | MTD | YTD)."""
    return dashboard_service.get_stats(db, tenant_id, period=period)


@router.get("/dashboard/vehicle-status")
def vehicle_status_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Vehicle-status distribution for the donut."""
    return dashboard_service.get_vehicle_status(db, tenant_id)


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
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Attention-required tiles (overdue returns / missing documents / overdue payments)."""
    return dashboard_service.get_attention(db, tenant_id)


@router.get("/dashboard/missing-documents")
def missing_documents_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """List of vehicles missing a required document (for the Attention slider)."""
    return dashboard_service.get_missing_documents(db, tenant_id)
