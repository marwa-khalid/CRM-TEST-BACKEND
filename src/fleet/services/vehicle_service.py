"""Fleet hire vehicle service."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHire, FleetHireVehicle, FleetVehicleRegister
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
    # is_active is the shared on-hire flag, but it can drift from reality — a hire
    # can be marked on_hire before its register row exists, so the row is either
    # missing or left inactive (this is why a vehicle can read "On Hire" on the
    # Skyline list yet "Available" in Vehicle Management). Reconcile it here from
    # the actual active hires — the same signal the Skyline list uses — so every
    # consumer agrees. Activate-only: never flip a row inactive (a vehicle may be
    # reserved on the Claims side without a fleet hire), so Claims state is safe.
    on_hire: dict = {}
    hv_rows = (
        db.query(FleetHireVehicle)
        .join(FleetHire, FleetHireVehicle.hire_id == FleetHire.id)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(func.lower(func.coalesce(FleetHireVehicle.hire_status, "")) == "on_hire")
        .all()
    )
    for hv in hv_rows:
        n = _normalise_registration(hv.registration_number)
        if n:
            on_hire.setdefault(n, hv)

    rows = db.query(FleetVehicleRegister).all()
    seen = set()
    changed = False
    for row in rows:
        n = _normalise_registration(row.registration_number)
        seen.add(n)
        if n in on_hire and not row.is_active:
            row.is_active = True
            changed = True
    for n, hv in on_hire.items():
        if n not in seen:
            db.add(FleetVehicleRegister(
                registration_number=hv.registration_number,
                make=hv.make or "",
                model=hv.model or "",
                transmission=hv.transmission or None,
                is_active=True,
            ))
            changed = True
    if changed:
        db.commit()

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
            # is_active is the shared Claims⇄Skyline on-hire flag. Honour it when the
            # caller sends it (Claims toggles availability through this endpoint);
            # existing Fleet make/model sync calls omit it and default to free.
            is_active=bool(data.get("is_active", False)),
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
        if "is_active" in data:
            row.is_active = bool(data.get("is_active"))

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
    # No register row yet — create one so an "on hire" activation isn't silently
    # dropped (the register row may not have been synced before the hire saved).
    if is_active:
        db.add(FleetVehicleRegister(registration_number=normalised, make="", model="", is_active=True))


def _sync_record_status_for_hire(db: Session, registration_number: Optional[str], on_hire: bool, hire_id: Optional[int] = None) -> None:
    """Keep the registered vehicle in step with its hire: on hire → status 'weekly_hire'
    and hire_id linked (so Current Hire Details can show the driver); off hire → status
    'available' and hire_id cleared. No-op when no Vehicle Management record matches."""
    from datetime import date as _date
    from fleet.models.tables import FleetVehicleRecord

    n = _normalise_registration(registration_number)
    if not n:
        return
    for rec in db.query(FleetVehicleRecord).filter(FleetVehicleRecord.is_deleted.isnot(True)).all():
        if _normalise_registration(rec.registration_number) == n:
            rec.vehicle_status = "weekly_hire" if on_hire else "available"
            rec.hire_id = hire_id if on_hire else None
            # Stamp the off-hire date (clear it when going back on hire) for the
            # dashboard's "off-hired today" filter.
            rec.off_hired_on = None if on_hire else _date.today()
            break


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
        _sync_record_status_for_hire(db, vehicle.registration_number, True, vehicle.hire_id)
    elif data.get("hire_status") == "off_hire":
        _set_register_activation(db, vehicle.registration_number, False)
        _sync_record_status_for_hire(db, vehicle.registration_number, False)

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
        _sync_record_status_for_hire(db, vehicle.registration_number, False)

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
