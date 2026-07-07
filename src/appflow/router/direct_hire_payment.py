from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.models.direct_hire_payment import (
    DirectHirePaymentIn,
    DirectHirePaymentOut,
    DirectHirePaymentGetOut,
)
from appflow.services.direct_hire_payment_service import DirectHirePaymentService
from appflow.utils import actor_id

direct_hire_payment_router = APIRouter(
    prefix="/direct-hire-payment",
    tags=["Direct Hire Payment"],
)


@direct_hire_payment_router.get("/{claim_id}", response_model=DirectHirePaymentGetOut)
def get_direct_hire_payment(claim_id: int, db: Session = Depends(get_session)):
    saved = DirectHirePaymentService.get_by_claim(claim_id, db)
    return {"saved": saved}


@direct_hire_payment_router.post("/", response_model=DirectHirePaymentOut)
def save_direct_hire_payment(
    payload: DirectHirePaymentIn,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    return DirectHirePaymentService.save(payload, db, current_user)
