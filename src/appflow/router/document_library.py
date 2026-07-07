from fastapi import APIRouter, Depends, File, Form, UploadFile, Query, HTTPException, Request
from typing import List, Optional
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from libdata.settings import get_session
from appflow.utils import actor_id, get_tenant_id
from appflow.models.document_library import (
    CaseDocumentListItemOut,
    CaseDocumentDetailOut,
    ShareLinkOut,
)
from appflow.services.document_library_service import DocumentLibraryService
from appflow.services.s3_service import S3Service

document_library_router = APIRouter(
    prefix="/document-library",
    tags=["Document Library"],
)


def _serialize_document_list(documents, request: Request):
    base_url = str(request.base_url).rstrip("/")
    output = []

    for document in documents:
        item = CaseDocumentListItemOut.model_validate(document).model_dump()
        local_key = item.get("file_url") or getattr(document, "s3_key", "")
        if S3Service.is_local_upload_key(local_key):
            item["file_url"] = f"{base_url}{S3Service.local_upload_public_path(local_key)}"
        output.append(item)

    return output


@document_library_router.get("/claim/{claim_id}", response_model=List[CaseDocumentListItemOut])
def list_case_documents(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    documents = DocumentLibraryService.list_case_documents(claim_id, db)
    return _serialize_document_list(documents, request)

@document_library_router.get("", response_model=List[CaseDocumentListItemOut])
@document_library_router.get("/", response_model=List[CaseDocumentListItemOut])
def list_documents_by_scope(
    request: Request,
    scope: str = Query("claim"),
    claim_id: Optional[int] = Query(None),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    if scope == "all":
        documents = DocumentLibraryService.list_all_documents(db, tenant_id)
        return _serialize_document_list(documents, request)

    if claim_id:
        documents = DocumentLibraryService.list_case_documents(claim_id, db)
        return _serialize_document_list(documents, request)

    raise HTTPException(
        status_code=400,
        detail="Use scope=all or provide claim_id",
    )

@document_library_router.get("/{document_id}", response_model=CaseDocumentDetailOut)
def get_document_detail(
    document_id: int,
    db: Session = Depends(get_session),
):
    return DocumentLibraryService.get_document_detail(document_id, db)

@document_library_router.get("/claim/{claim_id}/photos")
def list_claim_photos(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return DocumentLibraryService.list_claim_photos(claim_id, db)

class _EmailAttachmentIn(BaseModel):
    s3_key: str
    file_name: Optional[str] = None


class SendDocumentsEmailIn(BaseModel):
    to: str
    cc: Optional[str] = ""
    subject: Optional[str] = ""
    body: Optional[str] = ""
    attachments: List[_EmailAttachmentIn] = []


@document_library_router.post("/send-email")
def send_documents_email(
    payload: SendDocumentsEmailIn,
    current_user: int = Depends(actor_id),
):
    return DocumentLibraryService.send_documents_email(
        to=payload.to,
        cc=payload.cc or "",
        subject=payload.subject or "",
        body=payload.body or "",
        attachments=[a.model_dump() for a in payload.attachments],
    )


@document_library_router.post("/upload", response_model=CaseDocumentListItemOut)
def upload_document(
    claim_id: int = Form(...),
    category: str = Form(...),
    tag: str = Form(""),
    source_type: str = Form("user_upload"),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id),
):
    return DocumentLibraryService.upload_document(
        claim_id=claim_id,
        category=category,
        tag=tag,
        source_type=source_type,
        file=file,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
    )

@document_library_router.get("/{document_id}/preview-pages")
def get_document_preview_pages(
    document_id: int,
    compact: bool = Query(False),
    db: Session = Depends(get_session),
):
    return DocumentLibraryService.get_document_preview_pages(
        document_id,
        db,
        compact=compact,
    )

@document_library_router.post("/{document_id}/share-link", response_model=ShareLinkOut)
def create_share_link(
    document_id: int,
    expires_in_seconds: int = Form(3600),
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id),
):
    return DocumentLibraryService.create_share_link(
        document_id=document_id,
        expires_in_seconds=expires_in_seconds,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
    )


@document_library_router.post("/{document_id}/preview")
def register_preview(
    document_id: int,
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id),
):
    return DocumentLibraryService.register_preview(
        document_id=document_id,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
    )


@document_library_router.post("/{document_id}/download")
def register_download(
    document_id: int,
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id),
):
    return DocumentLibraryService.register_download(
        document_id=document_id,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
    )

@document_library_router.get("/{document_id}/presigned-url")
def get_presigned_file_url(
    document_id: int,
    request: Request,
    download: bool = Query(False),
    db: Session = Depends(get_session),
):
    return DocumentLibraryService.get_presigned_file_url(
        document_id,
        db,
        base_url=str(request.base_url),
        download=download,
    )
