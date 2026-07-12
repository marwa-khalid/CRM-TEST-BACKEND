from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import PaymentResponse, PaymentUpdate, ScheduleSync
from fleet.services import payment_service

router = APIRouter()


@router.get("/hire/{hire_id}/payments", response_model=List[PaymentResponse])
def list_payments_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.list_payments(db, hire_id, tenant_id)


@router.post("/hire/{hire_id}/payments/schedule", response_model=List[PaymentResponse])
def sync_schedule_route(
    hire_id: int,
    payload: ScheduleSync,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.sync_schedule(db, hire_id, tenant_id, payload.count, payload.due_amount)


@router.patch("/hire/{hire_id}/payments/{payment_id}", response_model=PaymentResponse)
def update_payment_route(
    hire_id: int,
    payment_id: int,
    payload: PaymentUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.update_payment(db, hire_id, tenant_id, payment_id, payload.model_dump(exclude_unset=True))
