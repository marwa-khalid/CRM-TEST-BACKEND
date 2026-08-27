from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import actor_id, get_session, get_tenant_id
from fleet.models.schemas import VehicleResponse, VehicleUpdate
from fleet.services import vehicle_service

# The shared vehicle register endpoints moved to the Vehicle Management module
# (src/vehicles, served under /vehicles). This router now owns only a hire's own
# vehicle cards (/hire/{hire_id}/vehicles), which stay a Fleet concern.
router = APIRouter()


@router.post("/hire/{hire_id}/vehicles", response_model=VehicleResponse)
def create_vehicle_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return vehicle_service.create_vehicle(db, hire_id, tenant_id, actor)


@router.get("/hire/{hire_id}/vehicles", response_model=List[VehicleResponse])
def list_vehicles_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return vehicle_service.list_vehicles(db, hire_id, tenant_id)


@router.patch("/hire/{hire_id}/vehicles/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle_route(
    hire_id: int,
    vehicle_id: int,
    payload: VehicleUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return vehicle_service.update_vehicle(db, hire_id, tenant_id, vehicle_id, payload.model_dump(exclude_unset=True), actor)


@router.delete("/hire/{hire_id}/vehicles/{vehicle_id}")
def delete_vehicle_route(
    hire_id: int,
    vehicle_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return vehicle_service.delete_vehicle(db, hire_id, tenant_id, vehicle_id)
