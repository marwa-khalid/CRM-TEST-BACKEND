from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.utils import get_tenant_id,actor_id
from appflow.models.insurer_broker import InsurerBrokerIn, InsurerBrokerOut
from appflow.services.insurer_broker_service import InsurerBrokerService

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