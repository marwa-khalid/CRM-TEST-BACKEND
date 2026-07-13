"""Fleet driver proof/document service."""
import mimetypes
from datetime import date
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import S3Service
from fleet.models.tables import FleetHireDocument
from fleet.services.common import get_hire_or_404


def add_document(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    actor_id: Optional[int],
    doc_type: str,
    file: UploadFile,
) -> FleetHireDocument:
    get_hire_or_404(db, hire_id, tenant_id)
    result = S3Service().upload_task_attachment_with_fallback(file)
    doc = FleetHireDocument(
        hire_id=hire_id,
        doc_type=doc_type,
        filename=getattr(file, "filename", None),
        s3_key=result.get("s3_key"),
        file_url=result.get("file_url"),
        storage_backend=result.get("storage_backend"),
        received_on=date.today(),
        created_by=actor_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_documents(db: Session, hire_id: int, tenant_id: Optional[int]):
    get_hire_or_404(db, hire_id, tenant_id)
    return (
        db.query(FleetHireDocument)
        .filter(FleetHireDocument.hire_id == hire_id)
        .order_by(FleetHireDocument.id)
        .all()
    )


def get_document_file(db: Session, hire_id: int, tenant_id: Optional[int], doc_id: int) -> Tuple[bytes, str, str]:
    """Return (bytes, media_type, filename) for a stored document — from S3 or the
    local /uploads fallback — so the frontend can display it (auth-checked)."""
    get_hire_or_404(db, hire_id, tenant_id)
    doc = (
        db.query(FleetHireDocument)
        .filter(FleetHireDocument.id == doc_id, FleetHireDocument.hire_id == hire_id)
        .first()
    )
    if not doc or not doc.s3_key:
        raise HTTPException(status_code=404, detail="Document not found")
    s3 = S3Service()
    try:
        if s3.is_local_upload_key(doc.s3_key):
            with open(s3.local_upload_filesystem_path(doc.s3_key), "rb") as f:
                data = f.read()
        else:
            data = s3.read_file_bytes(doc.s3_key)
    except Exception:  # pylint: disable=broad-exception-caught
        raise HTTPException(status_code=404, detail="File not available")
    media = mimetypes.guess_type(doc.filename or doc.s3_key)[0] or "application/octet-stream"
    return data, media, (doc.filename or "document")


def delete_document(db: Session, hire_id: int, tenant_id: Optional[int], doc_id: int) -> dict:
    get_hire_or_404(db, hire_id, tenant_id)
    doc = (
        db.query(FleetHireDocument)
        .filter(FleetHireDocument.id == doc_id, FleetHireDocument.hire_id == hire_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    return {"success": True}
