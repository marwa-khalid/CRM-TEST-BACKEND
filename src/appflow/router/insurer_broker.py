from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.utils import get_tenant_id,actor_id
from appflow.models.insurer_broker import InsurerBrokerIn, InsurerBrokerOut
from appflow.services.insurer_broker_service import InsurerBrokerService
from appflow.services.ocr_insurer_service import extract_certificate_text, parse_insurer_certificate

insurer_router = APIRouter(prefix="/insurer-brokers", tags=["Insurer Brokers"])


@insurer_router.get("/{claim_id}", response_model=List[InsurerBrokerOut])
def get_insurer_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return InsurerBrokerService.get_insurer_by_claim_id(claim_id, db)


@insurer_router.get("/{company_name}", response_model=List[InsurerBrokerOut])
def get_insurer_by_company(company_name: str, db: Session = Depends(get_session)):
    return InsurerBrokerService.get_insurer_by_company_name(company_name, db)


@insurer_router.post("/", response_model=InsurerBrokerOut)
def create_insurer_route(
    insurer: InsurerBrokerIn,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    current_user_id: int = Depends(actor_id)
):
    return InsurerBrokerService.create_insurer(insurer, db, tenant_id,current_user_id)


@insurer_router.put("/{claim_id}", response_model=InsurerBrokerOut)
def update_insurer_route(
    claim_id: int,
    insurer: InsurerBrokerIn,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    current_user_id: int = Depends(actor_id)
):
    return InsurerBrokerService.update_insurer(claim_id, insurer, db, tenant_id, current_user_id)


@insurer_router.patch("/{insurer_id}")
def deactivate_insurer_route(
    insurer_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return InsurerBrokerService.deactivate_insurer(insurer_id, db, tenant_id)


@insurer_router.get("/search/{query}", response_model=List[InsurerBrokerOut])
def search_insurers_route(
    query: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return InsurerBrokerService.search_insurers(query, db, tenant_id)
@insurer_router.get("/{claim_id}/policy-holder")
def read_policy_holder(claim_id: int, db: Session = Depends(get_session)):
    holder = InsurerBrokerService.get_policy_holder_by_claim(db, claim_id)
    if not holder:
        raise HTTPException(status_code=404, detail="Policy holder not found")
    return {"claim_id": claim_id, "policy_holder": holder}


@insurer_router.post("/certificate-ocr")
async def insurer_certificate_ocr(file: UploadFile = File(...)):
    """Read a Certificate of Motor Insurance (PDF/image) and return the fields for
    the Client Insurer form to pre-fill. Fields it can't read come back empty."""
    data = await file.read()
    text = extract_certificate_text(data, file.filename or "")
    return parse_insurer_certificate(text)


# ── Insurer company master (Company Name autocomplete) ───────────────────────
# Kept on a distinct prefix (not /insurer-brokers) so it can't collide with the
# insurer-broker claim/company routes, and so it reads as its own lookup like the
# referrer's /Referrers/companies/search.
insurer_company_router = APIRouter(prefix="/insurer-companies", tags=["Insurer Companies"])


class InsurerCompanyIn(BaseModel):
    company_name: str
    address: Optional[str] = None
    postcode: Optional[str] = None


@insurer_company_router.get("/search/{query}")
def search_insurer_companies_route(query: str, db: Session = Depends(get_session)):
    """Type-ahead suggestions for the Client Insurer Company Name field."""
    return InsurerBrokerService.search_insurer_companies(query, db)


@insurer_company_router.post("/")
def add_insurer_company_route(payload: InsurerCompanyIn, db: Session = Depends(get_session)):
    """Add a new insurer company to the master list (so users can create one that
    isn't in the seed data), mirroring the Referrer 'Add company' flow."""
    row = InsurerBrokerService.upsert_insurer_company(
        db, payload.company_name, payload.address, payload.postcode
    )
    if not row:
        raise HTTPException(status_code=400, detail="Company name is required")
    return {"id": row.id, "company_name": row.company_name, "address": row.address, "postcode": row.postcode}