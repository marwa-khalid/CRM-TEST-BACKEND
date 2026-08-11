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

    The customer side is the same hire as the client side, so match on the
    record's own hire first (reliable even before the customer-side Vehicle
    Details registration is filled from the V5C). Only fall back to matching by
    normalised registration when the record isn't linked to a hire.
    """
    record.latest_mileage_obtained = None
    record.mileage_obtained_on = None

    candidates = []
    if record.hire_id:
        # The hire's own vehicles, latest (most recently added) first.
        candidates = (
            db.query(FleetHireVehicle)
            .filter(FleetHireVehicle.hire_id == record.hire_id)
            .order_by(FleetHireVehicle.position.desc(), FleetHireVehicle.id.desc())
            .all()
        )
    if not candidates:
        reg = _normalise_reg(record.registration_number)
        if not reg:
            return record
        candidates = [
            v for v in (
                db.query(FleetHireVehicle)
                .filter(FleetHireVehicle.registration_number.isnot(None))
                .order_by(FleetHireVehicle.id.desc())
                .all()
            )
            if _normalise_reg(v.registration_number) == reg
        ]

    for vehicle in candidates:
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
    # Keep the shared vehicle register (the source for the Claims & Skyline hire
    # dropdowns) in step with the registered vehicle's identity fields.
    if (
        any(k in payload for k in ("registration_number", "make", "model", "transmission"))
        and record.registration_number
    ):
        from fleet.services import vehicle_service
        try:
            vehicle_service.upsert_vehicle_register(
                db,
                {
                    "registration_number": record.registration_number,
                    "make": record.make,
                    "model": record.model,
                    "transmission": record.transmission,
                },
            )
        except Exception:
            pass
    return _attach_mileage(db, record)


def delete_vehicle_record(db: Session, record_id: int, tenant_id: int) -> None:
    record = get_vehicle_record_or_404(db, record_id, tenant_id)
    record.is_deleted = True
    db.flush()
    # Remove the shared register entry too, so a deleted vehicle disappears from the reg
    # dropdowns and the Available count — unless another live record still uses the same reg.
    from fleet.services import vehicle_service
    from fleet.models.tables import FleetVehicleRegister

    reg = vehicle_service._normalise_registration(record.registration_number)
    if reg:
        others = (
            db.query(FleetVehicleRecord)
            .filter(FleetVehicleRecord.id != record_id)
            .filter(FleetVehicleRecord.is_deleted.isnot(True))
            .all()
        )
        still_used = any(vehicle_service._normalise_registration(r.registration_number) == reg for r in others)
        if not still_used:
            for row in db.query(FleetVehicleRegister).all():
                if vehicle_service._normalise_registration(row.registration_number) == reg:
                    db.delete(row)
    db.commit()
