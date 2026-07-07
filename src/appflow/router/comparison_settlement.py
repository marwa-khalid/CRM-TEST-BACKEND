from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from libdata.settings import get_session
from libdata.models.tables import User
from appflow.models.comparison_settlement import (
    ComparisonSettlementIn,
    ComparisonSettlementOut,
    ComparisonSettlementGetOut,
    DifferenceEmailIn,
)
from appflow.services.comparison_settlement_service import ComparisonSettlementService
from appflow.utils import actor_id

comparison_settlement_router = APIRouter(
    prefix="/comparison-settlement", tags=["Comparison Settlement"]
)


@comparison_settlement_router.get("/{claim_id}", response_model=ComparisonSettlementGetOut)
def get_comparison_settlement(
    claim_id: int, vehicle_id: int = None, db: Session = Depends(get_session)
):
    saved = ComparisonSettlementService.get_by_claim(claim_id, db, vehicle_id)
    saved_all = ComparisonSettlementService.get_all_by_claim(claim_id, db)
    system = ComparisonSettlementService.get_system_values(claim_id, db)
    return {"saved": saved, "saved_all": saved_all, "system": system}


@comparison_settlement_router.post("/", response_model=ComparisonSettlementOut)
def save_comparison_settlement(
    payload: ComparisonSettlementIn,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    return ComparisonSettlementService.save(payload, db, current_user)


@comparison_settlement_router.post("/send-difference-email")
def send_difference_email(
    payload: DifferenceEmailIn,
    request: Request,
    db: Session = Depends(get_session),
):
    # Recipient = the logged-in user (from the auth cookie), same as notify-manager,
    # unless the client explicitly supplied one. Avoids a 422 when the frontend
    # has no email in localStorage.
    if not payload.recipient_email:
        user = db.query(User).filter(User.id == actor_id(request)).first()
        payload.recipient_email = getattr(user, "user_name", None)
    return ComparisonSettlementService.send_difference_email(payload, db)
