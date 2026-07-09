"""Fleet hire service. Self-contained: does not import any Claims services, only
shared infra (DB models, S3Service)."""
from datetime import date
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from libdata.models.fleet_tables import FleetHire, FleetHireDocument
from appflow.services.s3_service import S3Service


def create_hire(db: Session, tenant_id: Optional[int], actor_id: Optional[int]) -> FleetHire:
    hire = FleetHire(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id)
    db.add(hire)
    db.commit()
    db.refresh(hire)
    return hire


def _get_hire_or_404(db: Session, hire_id: int, tenant_id: Optional[int]) -> FleetHire:
    q = db.query(FleetHire).filter(FleetHire.id == hire_id, FleetHire.is_deleted.isnot(True))
    if tenant_id is not None:
        q = q.filter(FleetHire.tenant_id == tenant_id)
    hire = q.first()
    if not hire:
        raise HTTPException(status_code=404, detail="Hire not found")
    return hire


def get_hire(db: Session, hire_id: int, tenant_id: Optional[int]) -> FleetHire:
    return _get_hire_or_404(db, hire_id, tenant_id)


def update_hire(db: Session, hire_id: int, tenant_id: Optional[int], actor_id: Optional[int], data: dict) -> FleetHire:
    """Apply a partial update (field-level save)."""
    hire = _get_hire_or_404(db, hire_id, tenant_id)
    for key, value in data.items():
        if hasattr(hire, key):
            setattr(hire, key, value)
    hire.updated_by = actor_id
    db.commit()
    db.refresh(hire)
    return hire


def add_document(db: Session, hire_id: int, tenant_id: Optional[int], actor_id: Optional[int],
                 doc_type: str, file: UploadFile) -> FleetHireDocument:
    _get_hire_or_404(db, hire_id, tenant_id)
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
    _get_hire_or_404(db, hire_id, tenant_id)
    return (
        db.query(FleetHireDocument)
        .filter(FleetHireDocument.hire_id == hire_id)
        .order_by(FleetHireDocument.id)
        .all()
    )


def delete_document(db: Session, hire_id: int, tenant_id: Optional[int], doc_id: int) -> dict:
    _get_hire_or_404(db, hire_id, tenant_id)
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
