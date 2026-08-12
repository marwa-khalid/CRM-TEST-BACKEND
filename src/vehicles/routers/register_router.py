"""Shared vehicle register endpoints (the pool that feeds the Claims & Skyline
hire reg dropdowns). Part of the Vehicle Management module — served under
/vehicles. The business logic still lives in fleet.services.vehicle_service and
is imported one-way (models/services stay in the fleet package)."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import get_session
from fleet.models.schemas import FleetVehicleRegisterResponse, FleetVehicleRegisterUpsert
from fleet.services import vehicle_service

router = APIRouter()


@router.get("/vehicle-register", response_model=List[FleetVehicleRegisterResponse])
def list_vehicle_register_route(
    context: Optional[str] = None,
    db: Session = Depends(get_session),
):
    return vehicle_service.list_vehicle_register(db, context)


@router.post("/vehicle-register", response_model=FleetVehicleRegisterResponse)
def upsert_vehicle_register_route(
    payload: FleetVehicleRegisterUpsert,
    db: Session = Depends(get_session),
):
    return vehicle_service.upsert_vehicle_register(db, payload.model_dump(exclude_unset=True))
