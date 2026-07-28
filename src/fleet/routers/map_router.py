from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import FleetVehicleLocationResponse
from fleet.services import map_service

router = APIRouter()


@router.get("/map/vehicles", response_model=List[FleetVehicleLocationResponse])
def list_map_vehicles_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Vehicle GPS positions for the Fleet Map (self-seeds demo data if empty)."""
    return map_service.list_vehicle_locations(db, tenant_id)
