"""Fleet weekly payment schedule service."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHirePayment
from fleet.services.common import get_hire_or_404


def list_payments(db: Session, hire_id: int, tenant_id: Optional[int]):
    get_hire_or_404(db, hire_id, tenant_id)
    return (
        db.query(FleetHirePayment)
        .filter(FleetHirePayment.hire_id == hire_id)
        .order_by(FleetHirePayment.week, FleetHirePayment.id)
        .all()
    )


def sync_schedule(db: Session, hire_id: int, tenant_id: Optional[int], count: int, due_amount: Optional[str]):
    """Ensure weeks 1..count exist with the given due amount; drop extra weeks.
    Preserves any recorded payment data on weeks that still exist."""
    get_hire_or_404(db, hire_id, tenant_id)
    count = max(0, int(count or 0))
    existing = {
        p.week: p
        for p in db.query(FleetHirePayment).filter(FleetHirePayment.hire_id == hire_id).all()
    }
    for week in range(1, count + 1):
        row = existing.get(week)
        if row:
            row.due_amount = due_amount
        else:
            db.add(FleetHirePayment(hire_id=hire_id, week=week, due_amount=due_amount, status="pending"))
    for week, row in existing.items():
        if week > count:
            db.delete(row)
    db.commit()
    return list_payments(db, hire_id, tenant_id)


def update_payment(db: Session, hire_id: int, tenant_id: Optional[int], payment_id: int, data: dict) -> FleetHirePayment:
    get_hire_or_404(db, hire_id, tenant_id)
    row = (
        db.query(FleetHirePayment)
        .filter(FleetHirePayment.id == payment_id, FleetHirePayment.hire_id == hire_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Payment not found")
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row
