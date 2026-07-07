from appflow.models.hire_detail import HireDetailListIn, HireDetailListOut
from appflow.services.hire_detail_service import HireDetailService
from fastapi import APIRouter, Depends,HTTPException
from libdata.settings import get_session
from sqlalchemy.orm import Session
from appflow.utils import actor_id,get_tenant_id

hire_detail_router = APIRouter(prefix="/hire-details", tags=["Hire Details"])


@hire_detail_router.post("/bulk", response_model=HireDetailListOut)
def create_hire_details(data: HireDetailListIn, db: Session = Depends(get_session),current_user=Depends(actor_id),tenant_id = Depends(get_tenant_id)):
    """
    Create hire detail records.
    Rules:
    - If single record: check ABI validation.
    - If multiple records: ensure previous record has hire_back before creating next.
    """
    created = HireDetailService.create_hire_details(data, db,current_user,tenant_id)
    return {"hire_details": created}


@hire_detail_router.get("/{claim_id}", response_model=HireDetailListOut)
def get_hire_details_by_claim(claim_id: int, db: Session = Depends(get_session)):
    """
    Fetch all active hire detail records by claim_id.
    """
    details = HireDetailService.get_hire_details_by_claim_id(claim_id, db)
    return {"hire_details": details}


@hire_detail_router.put("/{claim_id}", response_model=HireDetailListOut)
def update_hire_details_by_claim(claim_id: int, data: HireDetailListIn, db: Session = Depends(get_session),current_user=Depends(actor_id),tenant_id=Depends(get_tenant_id)):
    """
    Update existing and optionally add a new hire record.
    - Last existing record must have hire_back before adding new one.
    """
    updated = HireDetailService.update_hire_details_by_claim_id(claim_id, data, db,current_user,tenant_id)
    return {"hire_details": updated}


@hire_detail_router.put("/{claim_id}/deactivate")
def deactivate_hire_details_by_claim(claim_id: int, db: Session = Depends(get_session)):
    """
    Deactivate all hire detail records for a given claim_id.
    Sets is_active=False.
    """
    return HireDetailService.deactivate_hire_details_by_claim_id(claim_id, db)

@hire_detail_router.get("/hire-vehicle-provided/{hvp_id}")
def get_rates_from_hire_vehicle_provided(hvp_id: int, db: Session = Depends(get_session)):
    return HireDetailService.get_rates_from_hvp(hvp_id, db)