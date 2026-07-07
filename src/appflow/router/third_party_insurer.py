from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.orm import Session
from appflow.models.third_party_insurer import ThirdPartyInsurerIn, ThirdPartyInsurerOut
from appflow.services.third_party_insurer_service import ThirdPartyInsurerService
from libdata.settings import get_session

third_party_insurer_router = APIRouter(prefix="/third-party-insurer", tags=["Third Party Insurer"])

@third_party_insurer_router.post("/", response_model=ThirdPartyInsurerOut, status_code=status.HTTP_201_CREATED)
def create_third_party_insurer(payload: ThirdPartyInsurerIn, request: Request, db: Session = Depends(get_session)):
    return ThirdPartyInsurerService.create_third_party_insurer(request, payload, db)

@third_party_insurer_router.put("/{claim_id}", response_model=ThirdPartyInsurerOut)
def update_third_party_insurer(claim_id: int, payload: ThirdPartyInsurerIn,request: Request, db: Session = Depends(get_session)):
    return ThirdPartyInsurerService.update_third_party_insurer(claim_id, payload, db,request)

@third_party_insurer_router.get("/{claim_id}", response_model=ThirdPartyInsurerOut)
def get_third_party_insurer(claim_id: int, db: Session = Depends(get_session)):
    return ThirdPartyInsurerService.get_third_party_insurer(claim_id, db)

@third_party_insurer_router.patch("/deactivate/{claim_id}")
def deactivate_third_party_insurer(claim_id: int, db: Session = Depends(get_session)):
    return ThirdPartyInsurerService.deactivate_third_party_insurer(claim_id, db)
