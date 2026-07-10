"""Fleet module router. Self-contained under /fleet — no Claims router imports."""
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from fleet.deps import get_session
from fleet.deps import authenticate
from fleet.deps import get_tenant_id, actor_id
from fleet.models.schemas import HireUpdate, HireResponse, HireDocumentResponse
from fleet.services import hire_service as fleet_service
from fleet.services import ocr as fleet_ocr

# authenticate populates request.state (tenant_id/user_id) that the deps below read.
fleet_router = APIRouter(prefix="/fleet", tags=["Fleet"], dependencies=[Depends(authenticate)])


@fleet_router.post("/ocr/driving-licence")
async def ocr_driving_licence_route(file: UploadFile = File(...)):
    """OCR a driving-licence image/PDF -> driver fields (self-contained, free)."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_driving_licence(text)


@fleet_router.post("/ocr/proof-of-address")
async def ocr_proof_of_address_route(file: UploadFile = File(...)):
    """OCR a proof-of-address (utility bill) image/PDF -> {address, postcode}."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_proof_of_address(text)


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
