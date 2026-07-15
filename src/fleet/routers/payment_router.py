from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import (
    PaymentResponse,
    PaymentTransactionCreate,
    PaymentTransactionUpdate,
    PaymentUpdate,
    ScheduleSync,
)
from fleet.services import payment_service

router = APIRouter()


@router.get("/hire/{hire_id}/payments", response_model=List[PaymentResponse])
def list_payments_route(
    hire_id: int,
    vehicle_id: Optional[int] = Query(None),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.list_payments(db, hire_id, tenant_id, vehicle_id=vehicle_id)


@router.post("/hire/{hire_id}/payments/schedule", response_model=List[PaymentResponse])
def sync_schedule_route(
    hire_id: int,
    payload: ScheduleSync,
    vehicle_id: Optional[int] = Query(None),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.sync_schedule(
        db,
        hire_id,
        tenant_id,
        payload.count,
        payload.due_amount,
        payload.initial_due_amount,
        vehicle_id=vehicle_id,
    )


@router.patch("/hire/{hire_id}/payments/{payment_id}", response_model=PaymentResponse)
def update_payment_route(
    hire_id: int,
    payment_id: int,
    payload: PaymentUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.update_payment(db, hire_id, tenant_id, payment_id, payload.model_dump(exclude_unset=True))


@router.post("/hire/{hire_id}/payments/{payment_id}/transactions", response_model=PaymentResponse)
def add_transaction_route(
    hire_id: int,
    payment_id: int,
    payload: PaymentTransactionCreate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.add_transaction(db, hire_id, tenant_id, payment_id, payload.model_dump())


@router.patch("/hire/{hire_id}/payments/{payment_id}/transactions/{transaction_id}", response_model=PaymentResponse)
def update_transaction_route(
    hire_id: int,
    payment_id: int,
    transaction_id: int,
    payload: PaymentTransactionUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.update_transaction(
        db, hire_id, tenant_id, payment_id, transaction_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/hire/{hire_id}/payments/{payment_id}/transactions/{transaction_id}", response_model=PaymentResponse)
def delete_transaction_route(
    hire_id: int,
    payment_id: int,
    transaction_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return payment_service.delete_transaction(db, hire_id, tenant_id, payment_id, transaction_id)
