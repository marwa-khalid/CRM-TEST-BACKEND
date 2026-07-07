from typing import Optional

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session

from libdata.settings import get_session
from appflow.utils import get_tenant_id, actor_id
from appflow.services.dashboard_service import (
    get_dashboard, get_trends, get_income, get_missing_documents, get_storage_recovery,
    get_collection_performance, get_trend_options,
)

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@dashboard_router.get("")
def get_dashboard_route(
    request: Request,
    period: str = Query("ALL"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """Real aggregates for the dashboard (tenant-scoped). Urgent Alerts is scoped
    to the logged-in user's Overdue-status tasks."""
    return get_dashboard(db, get_tenant_id(request), period, start, end, actor_id(request))


@dashboard_router.get("/trends")
def get_trends_route(
    request: Request,
    period: str = Query("YTD"),
    mode: str = Query("YoY"),
    referrer: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    view: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """Claims + hired-vehicle trend for YoY / MoM comparisons, optionally
    filtered by referrer (source channel) and/or claim status. A CUSTOM period
    uses the start/end date range. `view` (summary|detail) drives the Claims
    Trend YoY/MoM drill-down."""
    return get_trends(db, get_tenant_id(request), period, mode, referrer, status, start, end, view)


@dashboard_router.get("/trend-options")
def trend_options_route(request: Request, db: Session = Depends(get_session)):
    """Referrer + status options for the trend filters."""
    return get_trend_options(db, get_tenant_id(request))


@dashboard_router.get("/income")
def get_income_route(
    request: Request,
    period: str = Query("ALL"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """Net income breakdown for a period (WTD / MTD / YTD / CUSTOM)."""
    return get_income(db, get_tenant_id(request), period, start, end)


@dashboard_router.get("/collection")
def get_collection_route(
    request: Request,
    period: str = Query("YTD"),
    payment_status: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """Collection Performance aggregate for period + Paid/Pending filter."""
    return get_collection_performance(db, get_tenant_id(request), period, payment_status)


@dashboard_router.get("/missing-documents")
def missing_documents_route(request: Request, db: Session = Depends(get_session)):
    """Every required document that's missing, per claim (for the slider)."""
    return get_missing_documents(db, get_tenant_id(request))


@dashboard_router.get("/storage-recovery")
def storage_recovery_route(request: Request, db: Session = Depends(get_session)):
    """Storage & Recovery summary + per-vehicle breakdown (for the sliders)."""
    return get_storage_recovery(db, get_tenant_id(request))
