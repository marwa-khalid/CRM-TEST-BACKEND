# app/routers/claims.py
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Query, Response
from sqlalchemy.orm import Session
from appflow.models.claims import (
    ClaimCreate, ClaimUpdate, ClaimOut, CloseClaimRequest, NotifyManagerRequest
)
from appflow.services.claims_service import (
    create_claim, get_claim, list_claims, update_claim, close_claim, notify_manager,deactivate_claim_service,restore_claim_service,list_claim_detail,convert_claims_to_csv
)
from libdata.settings import get_session
from appflow.utils import actor_id
from appflow.utils import get_tenant_id
from appflow.utils import build_case_reference
from io import StringIO
from fastapi.responses import StreamingResponse
from libdata.models.tables import Claim, User
from typing import Union
from pydantic import BaseModel

class Msg(BaseModel):
    detail: str


class ScreenCompletionUpdate(BaseModel):
    screen_key: str
    is_complete: bool

claims_router = APIRouter(prefix="/claims", tags=["Claims"])


def _get_claim_scoped(db: Session, claim_id: int, tenant_id):
    q = db.query(Claim).filter(Claim.id == claim_id)
    if tenant_id is not None:
        q = q.filter(Claim.tenant_id == tenant_id)
    return q.first()


@claims_router.post("")
def create_claim_route(payload: ClaimCreate, request: Request, db: Session = Depends(get_session)):
    claim = create_claim(db, payload.dict(exclude_unset=True), actor_id(request), get_tenant_id(request))
    setattr(claim, "labels", getattr(claim, "labels", None))
    return ClaimOut.model_validate(claim)

@claims_router.get("/claims-list")
def list_claim_details(request: Request, db: Session = Depends(get_session)):
    tenant_id = get_tenant_id(request)
    data = list_claim_detail(tenant_id, db)
    return data

@claims_router.get("/claims-list-csv")
def download_claims_csv(tenant_id: int, db: Session = Depends(get_session)):
    data = list_claim_detail(tenant_id, db)
    csv_data = convert_claims_to_csv(data)

    buffer = StringIO(csv_data)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=claims_list.csv"}
    )

@claims_router.get("/{claim_id}")
def get_claim_route(request: Request, claim_id: int, db: Session = Depends(get_session)):
    claim = get_claim(claim_id, get_tenant_id(request), db)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@claims_router.get("/{claim_id}/reference")
def get_claim_reference_route(claim_id: int, db: Session = Depends(get_session)):
    """Per-claim case reference (e.g. SURNAME-YYYYMM-00019) — derived server-side."""
    return {"reference": build_case_reference(claim_id, db)}


@claims_router.get("/{claim_id}/screen-completion")
def get_screen_completion_route(claim_id: int, request: Request, db: Session = Depends(get_session)):
    """Stored per-screen completion map for the claim sidebar's green checks."""
    claim = _get_claim_scoped(db, claim_id, get_tenant_id(request))
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return {"completion": claim.screen_completion or {}}


@claims_router.put("/{claim_id}/screen-completion")
def update_screen_completion_route(
    claim_id: int, payload: ScreenCompletionUpdate, request: Request,
    db: Session = Depends(get_session),
):
    """Upsert one screen's completion flag; returns the full updated map."""
    claim = _get_claim_scoped(db, claim_id, get_tenant_id(request))
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    # Reassign a new dict so SQLAlchemy detects the JSONB change (in-place mutation
    # of a JSON column is not tracked).
    current = dict(claim.screen_completion or {})
    current[payload.screen_key] = bool(payload.is_complete)
    claim.screen_completion = current
    db.commit()
    db.refresh(claim)
    return {"completion": claim.screen_completion or {}}


@claims_router.get("/list")
def list_claims_route(
        request: Request,
        db: Session = Depends(get_session),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        handler_id: Optional[int] = None,
        case_status_id: Optional[int] = None,
        search: Optional[str] = None,
):
    rows, total = list_claims(get_tenant_id(request), db, page=page, page_size=page_size,
                              handler_id=handler_id, case_status_id=case_status_id, search=search)
    # expose total via header for convenience
    # resp = [ClaimOut(**r.__dict__, labels=getattr(r, "labels", None)) for r in rows]  # type: ignore
    # NOTE: if you want to return total, either add a wrapper schema or set a header in a dependency
    return rows, total


@claims_router.put("/{claim_id}", response_model=ClaimOut)
def update_claim_route(claim_id: int,request: Request, payload: ClaimUpdate, db: Session = Depends(get_session)):
    user_id = actor_id(request)
    tenant_id = get_tenant_id(request)
    claim = update_claim(db, claim_id,user_id,tenant_id, payload.dict(exclude_unset=True))
    result = ClaimOut.model_validate(claim, from_attributes=True)
    result.labels = getattr(claim, "labels", None)
    return result


@claims_router.post("/{claim_id}/close", response_model=ClaimOut)
def close_claim_route(claim_id: int, payload: CloseClaimRequest, request: Request, db: Session = Depends(get_session)):
    claim = close_claim(db, claim_id, payload.reason, actor_id(request), get_tenant_id(request))
    return ClaimOut(**claim.__dict__, labels=getattr(claim, "labels", None))  # type: ignore


@claims_router.delete("/{claim_id}")
def deactivate_claim(claim_id: int, request: Request, db: Session = Depends(get_session)):
    return deactivate_claim_service(claim_id, request, db)


@claims_router.post("/{claim_id}/restore")
def restore_claim(claim_id: int, request: Request, db: Session = Depends(get_session)):
    return restore_claim_service(claim_id, request, db)


@claims_router.post("/{claim_id}/notify-manager", response_model=Union[ClaimOut, Msg])
def notify_manager_self_route(claim_id: int, request: Request, background_tasks: BackgroundTasks,
    db: Session = Depends(get_session)):
    # Recipient is the logged-in user (from the auth cookie) — no longer passed
    # from the client (localStorage was removed in the auth refactor).
    user = db.query(User).filter(User.id == actor_id(request)).first()
    email = getattr(user, "user_name", None)
    if not email:
        raise HTTPException(status_code=400, detail="No email for the current user")
    return notify_manager(db, claim_id, email, background_tasks)


@claims_router.post("/{claim_id}/notify-manager/{email}", response_model=Union[ClaimOut, Msg])
def notify_manager_route(claim_id: int,email:str, background_tasks: BackgroundTasks, # Added this
    db: Session = Depends(get_session)):
    claim = notify_manager(db, claim_id,email, background_tasks)
    return claim
    # return ClaimOut(**claim.__dict__, labels=getattr(claim, "labels", None))  # type: ignore
