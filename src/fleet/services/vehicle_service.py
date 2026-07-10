"""Fleet hire vehicle service."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHireVehicle
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
    db.commit()
    db.refresh(vehicle)
    return vehicle
