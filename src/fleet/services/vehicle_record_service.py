"""Fleet vehicle records (the vehicle asset wizard).

Section C (Current Mileage) is never stored on the record — the user story says it
is read-only and always fetched from the Skyline client side. So it is derived on
read from the most recent hire that used this registration.
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHireVehicle, FleetVehicleRecord


def _normalise_reg(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "") if ch.isalnum()).upper()


def _attach_mileage(db: Session, record: FleetVehicleRecord) -> FleetVehicleRecord:
    """Hang the latest client-side mileage off the record for the response model.

    Matching is done on a normalised registration because the two screens accept
    different spacing ("AB12 CDE" vs "AB12CDE").
    """
    record.latest_mileage_obtained = None
    record.mileage_obtained_on = None

    reg = _normalise_reg(record.registration_number)
    if not reg:
        return record

    candidates = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.registration_number.isnot(None))
        .order_by(FleetHireVehicle.id.desc())
        .all()
    )
    for vehicle in candidates:
        if _normalise_reg(vehicle.registration_number) != reg:
            continue
        # mileage_end is set at check-out (off hire); mileage_start at check-in.
        # The later of the two is the most recent reading we hold.
        mileage = (vehicle.mileage_end or "").strip() or (vehicle.mileage_start or "").strip()
        if not mileage:
            continue
        record.latest_mileage_obtained = mileage
        record.mileage_obtained_on = vehicle.checkout_date or vehicle.hire_end_date
        break
    return record


def create_vehicle_record(db: Session, tenant_id: int, actor: Optional[int] = None) -> FleetVehicleRecord:
    record = FleetVehicleRecord(tenant_id=tenant_id, created_by=actor, updated_by=actor)
    db.add(record)
    db.commit()
    db.refresh(record)
    return _attach_mileage(db, record)


def get_or_create_for_hire(
    db: Session, hire_id: int, tenant_id: int, actor: Optional[int] = None,
) -> FleetVehicleRecord:
    """The Customer Side of a hire file — one vehicle record per hire.

    Created on first open of a customer-side screen rather than when the hire is
    created, so existing hire files pick one up transparently.
    """
    record = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.hire_id == hire_id)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .order_by(FleetVehicleRecord.id)
        .first()
    )
    if not record:
        record = FleetVehicleRecord(
            tenant_id=tenant_id, hire_id=hire_id, created_by=actor, updated_by=actor,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    return _attach_mileage(db, record)


def list_vehicle_records(db: Session, tenant_id: int) -> List[FleetVehicleRecord]:
    records = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .filter(FleetVehicleRecord.tenant_id == tenant_id)
        .order_by(FleetVehicleRecord.id.desc())
        .all()
    )
    return [_attach_mileage(db, r) for r in records]


def get_vehicle_record_or_404(db: Session, record_id: int, tenant_id: int) -> FleetVehicleRecord:
    record = (
        db.query(FleetVehicleRecord)
        .filter(FleetVehicleRecord.id == record_id)
        .filter(FleetVehicleRecord.tenant_id == tenant_id)
        .filter(FleetVehicleRecord.is_deleted.isnot(True))
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Vehicle record not found.")
    return record


def get_vehicle_record(db: Session, record_id: int, tenant_id: int) -> FleetVehicleRecord:
    return _attach_mileage(db, get_vehicle_record_or_404(db, record_id, tenant_id))


def update_vehicle_record(
    db: Session,
    record_id: int,
    tenant_id: int,
    payload: dict,
    actor: Optional[int] = None,
) -> FleetVehicleRecord:
    record = get_vehicle_record_or_404(db, record_id, tenant_id)
    for field, value in payload.items():
        if hasattr(record, field):
            setattr(record, field, value)
    record.updated_by = actor
    db.commit()
    db.refresh(record)
    # Road tax expiry is derived from the renewal date, and drives a calendar
    # event + reminder schedule — rebuild both whenever the renewal date moves.
    if "road_tax_renewed_on" in payload:
        from fleet.services import road_fund_service
        record = road_fund_service.sync_expiry_and_event(db, record, actor)
    return _attach_mileage(db, record)


def delete_vehicle_record(db: Session, record_id: int, tenant_id: int) -> None:
    record = get_vehicle_record_or_404(db, record_id, tenant_id)
    record.is_deleted = True
    db.commit()
