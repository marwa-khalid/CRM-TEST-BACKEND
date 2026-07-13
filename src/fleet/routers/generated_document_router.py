from typing import List

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import GeneratedDocumentFileResponse
from fleet.services import generated_document_service

router = APIRouter()


@router.get(
    "/hire/{hire_id}/generated-documents/{document_key}",
    response_model=List[GeneratedDocumentFileResponse],
)
def list_generated_document_files_route(
    hire_id: int,
    document_key: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return generated_document_service.list_document_files(db, hire_id, tenant_id, document_key)


@router.get("/hire/{hire_id}/generated-documents/{document_key}/download")
def download_generated_document_route(
    hire_id: int,
    document_key: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    data, media, filename = generated_document_service.get_document_bundle(db, hire_id, tenant_id, document_key)
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/hire/{hire_id}/generated-documents/{document_key}/files/{file_key}")
def get_generated_document_file_route(
    hire_id: int,
    document_key: str,
    file_key: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    data, media, filename = generated_document_service.get_document_file(
        db,
        hire_id,
        tenant_id,
        document_key,
        file_key,
    )
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
