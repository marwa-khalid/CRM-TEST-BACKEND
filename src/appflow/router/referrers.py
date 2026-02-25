from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.utils import get_tenant_id
from appflow.models.referrers import (ReferrerCreate, ReferrerResponse,CompanySearchResponse)
from appflow.services.referrers_service import ReferrerService


referrers_router = APIRouter(prefix="/Referrers", tags=["Referrers & Commissions"])

# ======================= REFERRERS =======================
@referrers_router.get("/referrer/{claim_id}", response_model=ReferrerResponse)
def get_referrer(claim_id: int, db: Session = Depends(get_session)):
    return ReferrerService.get_referrer_by_claim_id(claim_id, db)

@referrers_router.get("/referrer/company/{company_name}", response_model=ReferrerResponse)
def get_referrer_by_company(company_name: str, db: Session = Depends(get_session)):
    return ReferrerService.get_referrer_by_company_name(company_name, db)

@referrers_router.post("/referrer", response_model=ReferrerResponse)
def create_referrer_route(referrer: ReferrerCreate,db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)):
    return ReferrerService.create_referrer(referrer, db, tenant_id)

@referrers_router.put("/referrer/{claim_id}", response_model=ReferrerResponse)
def update_referrer_route(claim_id: int, referrer: ReferrerCreate,
    db: Session = Depends(get_session), tenant_id: int = Depends(get_tenant_id)):
    return ReferrerService.update_referrer(claim_id, referrer, db, tenant_id)

@referrers_router.delete("/referrer/{referrer_id}")
def delete_referrer_route(
    referrer_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return ReferrerService.delete_referrer(referrer_id, db, tenant_id)

# @referrers_router.get("/referrer/search/{query}", response_model=List[ReferrerResponse])
# def search_referrers_route(
#     query: str,
#     db: Session = Depends(get_session),
#     tenant_id: int = Depends(get_tenant_id)
# ):
#     return ReferrerService.search_referrers(query, db, tenant_id)
@referrers_router.get(
    "/referrer/search/{query}",
    response_model=List[CompanySearchResponse]
)
def search_referrers_route(
    query: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return ReferrerService.search_referrers(query, db, tenant_id)

@referrers_router.get(
    "/companies/search/{query}",
    response_model=List[CompanySearchResponse]
)
def search_companies_route(
    query: str,
    db: Session = Depends(get_session),
):
    return ReferrerService.search_companies(query, db)
