from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.models.hire_payment_details import (
    HirePaymentDetailsIn,
    HirePaymentDetailsOut,
    HirePaymentDetailsGetOut,
)
from appflow.services.hire_payment_details_service import HirePaymentDetailsService
from appflow.utils import actor_id

hire_payment_details_router = APIRouter(
    prefix="/hire-payment-details",
    tags=["Hire Payment Details"],
)


@hire_payment_details_router.get("/{claim_id}", response_model=HirePaymentDetailsGetOut)
def get_hire_payment_details(claim_id: int, db: Session = Depends(get_session)):
    saved = HirePaymentDetailsService.get_by_claim(claim_id, db)
    return {"saved": saved}


@hire_payment_details_router.post("/", response_model=HirePaymentDetailsOut)
def save_hire_payment_details(
    payload: HirePaymentDetailsIn,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    result = HirePaymentDetailsService.save(payload, db, current_user)
    # (#10) Settlement saved on the payment screen -> notify the actor.
    try:
        from appflow.services.notification_service import safe_notify
        from appflow.utils import build_case_reference
        cid = getattr(payload, "claim_id", None)
        ref = build_case_reference(cid, db) if cid else ""
        safe_notify(
            db, recipient_user_id=current_user, actor_user_id=current_user,
            category="Claim", tab="Claims", title="Settlement Received",
            description=f"Settlement saved for {ref}." if ref else "Settlement was saved on the payment screen.",
            claim_id=cid,
        )
    except Exception:
        pass
    return result
