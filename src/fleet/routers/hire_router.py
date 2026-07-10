from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import actor_id, get_session, get_tenant_id
from fleet.models.schemas import HireAuditResponse, HireResponse, HireUpdate
from fleet.services import hire_service

router = APIRouter()


@router.post("/hire", response_model=HireResponse)
def create_hire_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return hire_service.create_hire(db, tenant_id, actor)


@router.get("/hire", response_model=List[HireResponse])
def list_hires_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return hire_service.list_hires(db, tenant_id)


@router.get("/hire/{hire_id}", response_model=HireResponse)
def get_hire_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return hire_service.get_hire(db, hire_id, tenant_id)


@router.patch("/hire/{hire_id}", response_model=HireResponse)
def update_hire_route(
    hire_id: int,
    payload: HireUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return hire_service.update_hire(db, hire_id, tenant_id, actor, payload.model_dump(exclude_unset=True))


@router.delete("/hire/{hire_id}")
def delete_hire_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return hire_service.delete_hire(db, hire_id, tenant_id)


@router.get("/hire/{hire_id}/audit", response_model=List[HireAuditResponse])
def list_audit_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return hire_service.list_audit(db, hire_id, tenant_id)
