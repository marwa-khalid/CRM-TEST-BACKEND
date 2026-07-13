from typing import List

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import actor_id, get_session, get_tenant_id
from fleet.models.schemas import HireDocumentResponse
from fleet.services import document_service

router = APIRouter()


@router.get("/hire/{hire_id}/documents/{doc_id}/file")
def get_document_file_route(
    hire_id: int,
    doc_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    data, media, filename = document_service.get_document_file(db, hire_id, tenant_id, doc_id)
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.post("/hire/{hire_id}/documents", response_model=HireDocumentResponse)
def add_document_route(
    hire_id: int,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return document_service.add_document(db, hire_id, tenant_id, actor, doc_type, file)


@router.get("/hire/{hire_id}/documents", response_model=List[HireDocumentResponse])
def list_documents_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return document_service.list_documents(db, hire_id, tenant_id)


@router.delete("/hire/{hire_id}/documents/{doc_id}")
def delete_document_route(
    hire_id: int,
    doc_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return document_service.delete_document(db, hire_id, tenant_id, doc_id)
