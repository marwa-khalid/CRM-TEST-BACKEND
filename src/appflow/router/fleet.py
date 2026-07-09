"""Fleet module router. Self-contained under /fleet — no Claims router imports."""
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from libdata.settings import get_session
from libauth.auth import authenticate
from appflow.utils import get_tenant_id, actor_id
from appflow.models.fleet import HireUpdate, HireResponse, HireDocumentResponse
from appflow.services import fleet_service

# authenticate populates request.state (tenant_id/user_id) that the deps below read.
fleet_router = APIRouter(prefix="/fleet", tags=["Fleet"], dependencies=[Depends(authenticate)])


@fleet_router.post("/hire", response_model=HireResponse)
def create_hire_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return fleet_service.create_hire(db, tenant_id, actor)


@fleet_router.get("/hire/{hire_id}", response_model=HireResponse)
def get_hire_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return fleet_service.get_hire(db, hire_id, tenant_id)


@fleet_router.patch("/hire/{hire_id}", response_model=HireResponse)
def update_hire_route(
    hire_id: int,
    payload: HireUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return fleet_service.update_hire(db, hire_id, tenant_id, actor, payload.model_dump(exclude_unset=True))


@fleet_router.post("/hire/{hire_id}/documents", response_model=HireDocumentResponse)
def add_document_route(
    hire_id: int,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return fleet_service.add_document(db, hire_id, tenant_id, actor, doc_type, file)


@fleet_router.get("/hire/{hire_id}/documents", response_model=List[HireDocumentResponse])
def list_documents_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return fleet_service.list_documents(db, hire_id, tenant_id)


@fleet_router.delete("/hire/{hire_id}/documents/{doc_id}")
def delete_document_route(
    hire_id: int,
    doc_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return fleet_service.delete_document(db, hire_id, tenant_id, doc_id)
