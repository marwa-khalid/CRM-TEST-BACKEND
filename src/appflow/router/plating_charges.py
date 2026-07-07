from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from libdata.settings import get_session
from appflow.models.plating_charges import PlatingChargesIn, PlatingChargesOut
from appflow.services.plating_charges_service import PlatingChargesService
from appflow.utils import actor_id

plating_charges_router = APIRouter(prefix="/plating-charges", tags=["Plating & Additional Charges"])


@plating_charges_router.get("/{claim_id}", response_model=Optional[PlatingChargesOut])
def get_plating_charges(
    claim_id: int,
    vehicle_id: Optional[int] = Query(None),
    db: Session = Depends(get_session),
):
    return PlatingChargesService.get_by_claim(claim_id, db, vehicle_id)


@plating_charges_router.get("/{claim_id}/total")
def get_plating_total(claim_id: int, db: Session = Depends(get_session)):
    """Total plating across all of the claim's vehicles (for the Billed Breakdown)."""
    return {"total_plating_cost": PlatingChargesService.get_total(claim_id, db)}


@plating_charges_router.post("/", response_model=PlatingChargesOut)
def save_plating_charges(
    payload: PlatingChargesIn,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    return PlatingChargesService.save(payload, db, current_user)
