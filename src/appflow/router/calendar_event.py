from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session

from libdata.settings import get_session
from appflow.models.calendar_event import CalendarEventIn, CalendarEventOut
from appflow.services.calendar_event_service import CalendarEventService
from appflow.utils import actor_id, get_tenant_id

calendar_event_router = APIRouter(prefix="/calendar-events", tags=["Calendar Events"])


@calendar_event_router.get("", response_model=list[CalendarEventOut])
def list_calendar_events(
    request: Request,
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    event_type: Optional[str] = Query(None),
    assigned_user: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    claim_reference: Optional[str] = Query(None),
    vehicle_registration: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    return CalendarEventService.list_events(
        db, get_tenant_id(request), start, end, event_type, assigned_user,
        department, claim_reference, vehicle_registration, search, status,
        current_user=actor_id(request),
    )


@calendar_event_router.post("", response_model=CalendarEventOut)
def create_calendar_event(
    payload: CalendarEventIn, request: Request, db: Session = Depends(get_session),
):
    return CalendarEventService.create_event(payload, db, actor_id(request), get_tenant_id(request))


@calendar_event_router.get("/{event_id}", response_model=CalendarEventOut)
def get_calendar_event(event_id: int, request: Request, db: Session = Depends(get_session)):
    return CalendarEventService.get_event(db, event_id, get_tenant_id(request))


@calendar_event_router.put("/{event_id}", response_model=CalendarEventOut)
def update_calendar_event(
    event_id: int, payload: CalendarEventIn, request: Request, db: Session = Depends(get_session),
):
    return CalendarEventService.update_event(event_id, payload, db, actor_id(request), get_tenant_id(request))


@calendar_event_router.post("/{event_id}/complete", response_model=CalendarEventOut)
def complete_calendar_event(
    event_id: int, request: Request,
    occurrence_date: Optional[date] = Query(None),
    db: Session = Depends(get_session),
):
    return CalendarEventService.set_status(
        event_id, "Completed", db, actor_id(request), get_tenant_id(request), occurrence_date,
    )


@calendar_event_router.post("/{event_id}/cancel", response_model=CalendarEventOut)
def cancel_calendar_event(
    event_id: int, request: Request,
    occurrence_date: Optional[date] = Query(None),
    db: Session = Depends(get_session),
):
    return CalendarEventService.set_status(
        event_id, "Cancelled", db, actor_id(request), get_tenant_id(request), occurrence_date,
    )


@calendar_event_router.get("/{event_id}/audit")
def calendar_event_audit(event_id: int, request: Request, db: Session = Depends(get_session)):
    return CalendarEventService.get_audit(db, event_id, get_tenant_id(request))


@calendar_event_router.delete("/{event_id}")
def delete_calendar_event(
    event_id: int, request: Request,
    occurrence_date: Optional[date] = Query(None),
    db: Session = Depends(get_session),
):
    return CalendarEventService.delete_event(
        event_id, db, actor_id(request), get_tenant_id(request), occurrence_date,
    )
