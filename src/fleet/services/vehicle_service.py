"""Fleet hire vehicle service."""
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHireVehicle
from fleet.services.common import get_hire_or_404
from fleet.services.sms_service import send_on_hire_sms

logger = logging.getLogger(__name__)


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
    hire = get_hire_or_404(db, hire_id, tenant_id)
    vehicle = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.id == vehicle_id, FleetHireVehicle.hire_id == hire_id)
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    previous_status = vehicle.hire_status
    should_send_on_hire_sms = data.get("hire_status") == "on_hire" and previous_status != "on_hire"

    for key, value in data.items():
        if hasattr(vehicle, key):
            setattr(vehicle, key, value)
    db.commit()
    db.refresh(vehicle)

    if should_send_on_hire_sms:
        result = send_on_hire_sms(hire.driver_mobile)
        if result.get("sent"):
            logger.info("Fleet on-hire SMS sent for hire_id=%s vehicle_id=%s", hire_id, vehicle_id)
        else:
            logger.warning("Fleet on-hire SMS not sent for hire_id=%s vehicle_id=%s: %s", hire_id, vehicle_id, result)

    return vehicle
