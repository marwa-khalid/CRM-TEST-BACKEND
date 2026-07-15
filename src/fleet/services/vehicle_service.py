"""Fleet hire vehicle service."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHireVehicle, FleetVehicleRegister
from fleet.services.common import get_hire_or_404

def create_vehicle(db: Session, hire_id: int, tenant_id: Optional[int], actor_id: Optional[int]) -> FleetHireVehicle:
    get_hire_or_404(db, hire_id, tenant_id)
    position = db.query(FleetHireVehicle).filter(FleetHireVehicle.hire_id == hire_id).count()
    vehicle = FleetHireVehicle(hire_id=hire_id, position=position, created_by=actor_id)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def list_vehicles(db: Session, hire_id: int, tenant_id: Optional[int]):
    get_hire_or_404(db, hire_id, tenant_id)
    return (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.hire_id == hire_id)
        .order_by(FleetHireVehicle.position, FleetHireVehicle.id)
        .all()
    )


def list_vehicle_register(db: Session):
    return (
        db.query(FleetVehicleRegister)
        .order_by(FleetVehicleRegister.registration_number.asc())
        .all()
    )


def _normalise_registration(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def upsert_vehicle_register(db: Session, data: dict) -> FleetVehicleRegister:
    registration_number = _normalise_registration(data.get("registration_number"))
    if not registration_number:
        raise HTTPException(status_code=422, detail="Registration number is required")

    row = None
    for existing in db.query(FleetVehicleRegister).all():
        if _normalise_registration(existing.registration_number) == registration_number:
            row = existing
            break

    if row is None:
        row = FleetVehicleRegister(
            registration_number=registration_number,
            make=data.get("make") or "",
            model=data.get("model") or "",
            transmission=data.get("transmission") or None,
            is_active=False,
        )
        db.add(row)
    else:
        row.registration_number = registration_number
        if "make" in data:
            row.make = data.get("make") or ""
        if "model" in data:
            row.model = data.get("model") or ""
        if "transmission" in data:
            row.transmission = data.get("transmission") or None

    db.commit()
    db.refresh(row)
    return row


def _sync_register_details(db: Session, vehicle: FleetHireVehicle):
    if not _normalise_registration(vehicle.registration_number):
        return
    upsert_vehicle_register(db, {
        "registration_number": vehicle.registration_number,
        "make": vehicle.make,
        "model": vehicle.model,
        "transmission": vehicle.transmission,
    })


def _set_register_activation(db: Session, registration_number: Optional[str], is_active: bool):
    normalised = _normalise_registration(registration_number)
    if not normalised:
        return

    rows = db.query(FleetVehicleRegister).all()
    for row in rows:
        if _normalise_registration(row.registration_number) == normalised:
            row.is_active = is_active
            return


def update_vehicle(db: Session, hire_id: int, tenant_id: Optional[int], vehicle_id: int, data: dict) -> FleetHireVehicle:
    get_hire_or_404(db, hire_id, tenant_id)
    vehicle = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.id == vehicle_id, FleetHireVehicle.hire_id == hire_id)
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    for key, value in data.items():
        if hasattr(vehicle, key):
            setattr(vehicle, key, value)

    if {"registration_number", "make", "model", "transmission"} & set(data.keys()):
        _sync_register_details(db, vehicle)

    if data.get("hire_status") == "on_hire":
        _set_register_activation(db, vehicle.registration_number, True)
    elif data.get("hire_status") == "off_hire":
        _set_register_activation(db, vehicle.registration_number, False)

    db.commit()
    db.refresh(vehicle)

    return vehicle


def delete_vehicle(db: Session, hire_id: int, tenant_id: Optional[int], vehicle_id: int) -> dict:
    get_hire_or_404(db, hire_id, tenant_id)
    vehicle = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.id == vehicle_id, FleetHireVehicle.hire_id == hire_id)
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    if vehicle.hire_status == "on_hire":
        _set_register_activation(db, vehicle.registration_number, False)

    db.delete(vehicle)
    db.flush()

    remaining = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.hire_id == hire_id)
        .order_by(FleetHireVehicle.position, FleetHireVehicle.id)
        .all()
    )
    for index, row in enumerate(remaining):
        row.position = index

    db.commit()
    return {"status": "deleted"}
