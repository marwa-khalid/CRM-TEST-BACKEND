# app/routers/claims.py
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Query, Response
from sqlalchemy.orm import Session
from appflow.models.claims import (
    ClaimCreate, ClaimUpdate, ClaimOut, CloseClaimRequest, NotifyManagerRequest
)
from appflow.services.claims_service import (
    create_claim, get_claim, list_claims, update_claim, close_claim, notify_manager,deactivate_claim_service
)
from libdata.settings import get_session
from appflow.utils import actor_id
from appflow.utils import get_tenant_id

from libdata.models.tables import Claim

claims_router = APIRouter(prefix="/claims", tags=["Claims"])


@claims_router.post("")
def create_claim_route(payload: ClaimCreate, request: Request, db: Session = Depends(get_session)):
    claim = create_claim(db, payload.dict(exclude_unset=True), actor_id(request), get_tenant_id(request))
    return ClaimOut(**claim.__dict__, labels=getattr(claim, "labels", None))  # type: ignore


@claims_router.get("/{claim_id}")
def get_claim_route(request: Request, claim_id: int, db: Session = Depends(get_session)):
    claim = get_claim(claim_id, get_tenant_id(request), db)
    return claim


@claims_router.get("/list")
def list_claims_route(
    request: Request,
    db: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    handler_id: Optional[int] = Query(None, ge=1),
    case_status_id: Optional[int] = Query(None, ge=1),
    search: Optional[str] = None,
):
    rows, total = list_claims(get_tenant_id(request), db, page=page, page_size=page_size,
                              handler_id=handler_id, case_status_id=case_status_id, search=search)
    return {"rows": rows, "total": total}


@claims_router.put("/{claim_id}", response_model=ClaimOut)
def update_claim_route(claim_id: int, payload: ClaimUpdate, db: Session = Depends(get_session)):
    claim = update_claim(db, claim_id, payload.dict(exclude_unset=True))
    return ClaimOut(**claim.__dict__, labels=getattr(claim, "labels", None))  # type: ignore


@claims_router.post("/{claim_id}/close", response_model=ClaimOut)
def close_claim_route(claim_id: int, payload: CloseClaimRequest, db: Session = Depends(get_session)):
    claim = close_claim(db, claim_id, payload.reason)
    return ClaimOut(**claim.__dict__, labels=getattr(claim, "labels", None))  # type: ignore


@claims_router.delete("/{claim_id}")
def deactivate_claim(claim_id: int, request: Request, db: Session = Depends(get_session)):
    return deactivate_claim_service(claim_id, request, db)


# @claims_router.post("/{claim_id}/notify-manager", response_model=ClaimOut)
# def notify_manager_route(claim_id: int, payload: NotifyManagerRequest, db: Session = Depends(get_session)):
#     claim = notify_manager(db, claim_id, payload.note)
#     return ClaimOut(**claim.__dict__, labels=getattr(claim, "labels", None))  # type: ignore

@claims_router.post("/{claim_id}/notify-manager", response_model=ClaimOut)
def notify_manager_route(
    claim_id: int, 
    background_tasks: BackgroundTasks, # Added this
    db: Session = Depends(get_session)
):
    claim = notify_manager(db, claim_id, background_tasks)
    return ClaimOut(**claim.__dict__, labels=getattr(claim, "labels", None))