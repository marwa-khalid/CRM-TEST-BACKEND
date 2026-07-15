"""Fleet weekly payment schedule service."""
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHirePayment, FleetHirePaymentTransaction, FleetHireVehicle
from fleet.services.common import get_hire_or_404


def _num(value) -> float:
    """Parse a money-ish string ('£1,234.50') into a float; non-numbers → 0."""
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(value or "")) or 0)
    except ValueError:
        return 0.0


def _recompute_week(row: FleetHirePayment) -> None:
    """Roll the week's transactions up into its summary fields: paid_amount is the
    sum of transactions, status is derived from due vs paid, and the date/time
    mirror the most recent transaction so the schedule table shows one line."""
    txns = sorted(row.transactions, key=lambda t: t.id)
    total = sum(_num(t.amount) for t in txns)
    due = _num(row.due_amount)
    row.paid_amount = f"{total:.2f}" if txns else None
    if total <= 0:
        row.status = "pending"
    elif due > 0 and total < due:
        row.status = "partial"
    else:
        row.status = "received"
    latest = txns[-1] if txns else None
    row.payment_date = latest.payment_date if latest else None
    row.payment_time = latest.payment_time if latest else None


def _validate_vehicle(db: Session, hire_id: int, vehicle_id: Optional[int]) -> None:
    if vehicle_id is None:
        return
    exists = (
        db.query(FleetHireVehicle.id)
        .filter(FleetHireVehicle.id == vehicle_id, FleetHireVehicle.hire_id == hire_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Vehicle not found")


def _scope_vehicle(query, vehicle_id: Optional[int]):
    if vehicle_id is None:
        return query.filter(FleetHirePayment.vehicle_id.is_(None))
    return query.filter(FleetHirePayment.vehicle_id == vehicle_id)


def list_payments(db: Session, hire_id: int, tenant_id: Optional[int], vehicle_id: Optional[int] = None):
    get_hire_or_404(db, hire_id, tenant_id)
    _validate_vehicle(db, hire_id, vehicle_id)
    return (
        _scope_vehicle(
            db.query(FleetHirePayment).filter(FleetHirePayment.hire_id == hire_id),
            vehicle_id,
        )
        .order_by(FleetHirePayment.week, FleetHirePayment.id)
        .all()
    )


def sync_schedule(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    count: int,
    due_amount: Optional[str],
    initial_due_amount: Optional[str] = None,
    vehicle_id: Optional[int] = None,
):
    """Ensure weeks 1..count exist with the given due amount; drop extra weeks.
    Preserves any recorded payment data on weeks that still exist."""
    get_hire_or_404(db, hire_id, tenant_id)
    _validate_vehicle(db, hire_id, vehicle_id)
    count = max(0, int(count or 0))
    existing = {
        p.week: p
        for p in _scope_vehicle(
            db.query(FleetHirePayment).filter(FleetHirePayment.hire_id == hire_id),
            vehicle_id,
        ).all()
    }
    for week in range(1, count + 1):
        row_due_amount = initial_due_amount if week == 1 and initial_due_amount is not None else due_amount
        row = existing.get(week)
        if row:
            row.due_amount = row_due_amount
        else:
            db.add(FleetHirePayment(
                hire_id=hire_id,
                vehicle_id=vehicle_id,
                week=week,
                due_amount=row_due_amount,
                status="pending",
            ))
    for week, row in existing.items():
        if week > count:
            db.delete(row)
    db.commit()
    return list_payments(db, hire_id, tenant_id, vehicle_id=vehicle_id)


def _get_payment_or_404(db: Session, hire_id: int, payment_id: int) -> FleetHirePayment:
    row = (
        db.query(FleetHirePayment)
        .filter(FleetHirePayment.id == payment_id, FleetHirePayment.hire_id == hire_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Payment not found")
    return row


def update_payment(db: Session, hire_id: int, tenant_id: Optional[int], payment_id: int, data: dict) -> FleetHirePayment:
    get_hire_or_404(db, hire_id, tenant_id)
    row = _get_payment_or_404(db, hire_id, payment_id)
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    # If the due amount changed, the paid/partial status may need refreshing.
    if "due_amount" in data:
        _recompute_week(row)
    db.commit()
    db.refresh(row)
    return row


def add_transaction(
    db: Session, hire_id: int, tenant_id: Optional[int], payment_id: int, data: dict
) -> FleetHirePayment:
    """Append one dated payment to a week and roll the week's totals back up."""
    get_hire_or_404(db, hire_id, tenant_id)
    row = _get_payment_or_404(db, hire_id, payment_id)
    row.transactions.append(
        FleetHirePaymentTransaction(
            amount=data.get("amount"),
            payment_mode=data.get("payment_mode") or "cash",
            payment_date=data.get("payment_date"),
            payment_time=data.get("payment_time"),
            notes=data.get("notes"),
        )
    )
    db.flush()  # assign the new transaction an id before recomputing order
    _recompute_week(row)
    db.commit()
    db.refresh(row)
    return row


def update_transaction(
    db: Session, hire_id: int, tenant_id: Optional[int], payment_id: int, transaction_id: int, data: dict
) -> FleetHirePayment:
    """Edit an existing payment (amount / mode / date / notes) and roll the week's
    totals back up. Lets users correct a mistake instead of only adding more."""
    get_hire_or_404(db, hire_id, tenant_id)
    row = _get_payment_or_404(db, hire_id, payment_id)
    txn = next((t for t in row.transactions if t.id == transaction_id), None)
    if not txn:
        raise HTTPException(status_code=404, detail="Payment transaction not found")
    for key, value in data.items():
        if hasattr(txn, key):
            setattr(txn, key, value)
    db.flush()
    _recompute_week(row)
    db.commit()
    db.refresh(row)
    return row


def delete_transaction(
    db: Session, hire_id: int, tenant_id: Optional[int], payment_id: int, transaction_id: int
) -> FleetHirePayment:
    """Remove one payment from a week and roll the week's totals back down."""
    get_hire_or_404(db, hire_id, tenant_id)
    row = _get_payment_or_404(db, hire_id, payment_id)
    txn = next((t for t in row.transactions if t.id == transaction_id), None)
    if not txn:
        raise HTTPException(status_code=404, detail="Payment transaction not found")
    row.transactions.remove(txn)
    db.flush()
    _recompute_week(row)
    db.commit()
    db.refresh(row)
    return row
