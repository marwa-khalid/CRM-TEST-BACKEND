from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from libdata.settings import get_session
from appflow.models.driver_documents_agreements import (
    DriverDocumentAgreementBase,
    DriverDocumentAgreementCreate,
    DriverDocumentAgreementOut,
    DriverDocumentUploadOut,
)
from appflow.services.driver_document_agreement_service import DriverDocumentAgreementService
from appflow.utils import actor_id, get_tenant_id


driver_documents_router = APIRouter(
    prefix="/driver-documents",
    tags=["Driver Documents & Agreements"],
)


@driver_documents_router.post(
    "/",
    response_model=DriverDocumentAgreementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_driver_documents(
    payload: DriverDocumentAgreementCreate,
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id),
):
    return DriverDocumentAgreementService.create(payload, db, user_id, tenant_id)


@driver_documents_router.get(
    "/{claim_id}",
    response_model=DriverDocumentAgreementOut,
    status_code=status.HTTP_200_OK,
)
def get_driver_documents(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return DriverDocumentAgreementService.get_by_claim(claim_id, db)


@driver_documents_router.put(
    "/{claim_id}",
    response_model=DriverDocumentAgreementOut,
    status_code=status.HTTP_200_OK,
)
def update_driver_document(
    claim_id: int,
    payload: DriverDocumentAgreementBase,
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id),
):
    return DriverDocumentAgreementService.update_by_claim_id(
        claim_id, payload, db, user_id, tenant_id
    )


@driver_documents_router.post(
    "/{claim_id}/upload",
    response_model=DriverDocumentUploadOut,
    status_code=status.HTTP_200_OK,
)
def upload_driver_document(
    claim_id: int,
    field_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id),
):
    return DriverDocumentAgreementService.upload_document_for_claim(
        claim_id=claim_id,
        field_name=field_name,
        file=file,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
    )


@driver_documents_router.delete("/{claim_id}")
def deactivate_driver_document(
    claim_id: int,
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
):
    return DriverDocumentAgreementService.deactivate_by_claim_id(claim_id, db, user_id)