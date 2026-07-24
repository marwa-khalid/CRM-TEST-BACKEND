"""Files uploaded against a vehicle record (V5C history).

Every upload is a new row, so replacing a V5C keeps the previous one viewable
with its own timestamp — the screen shows the full upload history.
"""
import mimetypes
from typing import List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import S3Service
from fleet.models.tables import FleetVehicleDocument


def add_document(
    db: Session, vehicle_record_id: int, file: UploadFile, doc_type: str = "v5c",
    actor: Optional[int] = None, authority_id: Optional[int] = None,
) -> FleetVehicleDocument:
    result = S3Service().upload_task_attachment_with_fallback(file)
    doc = FleetVehicleDocument(
        vehicle_record_id=vehicle_record_id,
        doc_type=doc_type,
        authority_id=authority_id,
        filename=getattr(file, "filename", None),
        s3_key=result.get("s3_key"),
        file_url=result.get("file_url"),
        storage_backend=result.get("storage_backend"),
        created_by=actor,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def add_stored_document(
    db: Session, vehicle_record_id: int, *, doc_type: str, filename, s3_key, file_url,
    storage_backend=None, authority_id: Optional[int] = None,
    service_id: Optional[int] = None, actor: Optional[int] = None,
) -> FleetVehicleDocument:
    """Record a history row for a file already uploaded to S3 (no re-upload)."""
    doc = FleetVehicleDocument(
        vehicle_record_id=vehicle_record_id, doc_type=doc_type, authority_id=authority_id,
        service_id=service_id, filename=filename, s3_key=s3_key, file_url=file_url,
        storage_backend=storage_backend, created_by=actor,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_documents(
    db: Session, vehicle_record_id: int, doc_type: Optional[str] = None,
    authority_id: Optional[int] = None, service_id: Optional[int] = None,
) -> List[FleetVehicleDocument]:
    """Newest first, so the most recent upload heads the history."""
    query = db.query(FleetVehicleDocument).filter(
        FleetVehicleDocument.vehicle_record_id == vehicle_record_id
    )
    if doc_type:
        query = query.filter(FleetVehicleDocument.doc_type == doc_type)
    if authority_id is not None:
        query = query.filter(FleetVehicleDocument.authority_id == authority_id)
    if service_id is not None:
        query = query.filter(FleetVehicleDocument.service_id == service_id)
    return query.order_by(FleetVehicleDocument.id.desc()).all()


def get_document_file(db: Session, vehicle_record_id: int, doc_id: int) -> Tuple[bytes, str, str]:
    doc = (
        db.query(FleetVehicleDocument)
        .filter(FleetVehicleDocument.id == doc_id)
        .filter(FleetVehicleDocument.vehicle_record_id == vehicle_record_id)
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
