"""Penalty Charges / PCN service."""
from datetime import date
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import S3Service
from fleet.models.tables import FleetHireAudit, FleetPcn, FleetPcnDocument, FleetPcnNote, FleetPcnReminder
from fleet.services.common import actor_name_for, get_hire_or_404, norm


def get_or_create_pcn(db: Session, hire_id: int, tenant_id: Optional[int], actor_id: Optional[int] = None) -> FleetPcn:
    get_hire_or_404(db, hire_id, tenant_id)
    pcn = db.query(FleetPcn).filter(FleetPcn.hire_id == hire_id).first()
    if pcn:
        return pcn

    pcn = FleetPcn(hire_id=hire_id, tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id)
    db.add(pcn)
    db.commit()
    db.refresh(pcn)
    return pcn


def get_pcn(db: Session, hire_id: int, tenant_id: Optional[int], actor_id: Optional[int] = None) -> FleetPcn:
    return get_or_create_pcn(db, hire_id, tenant_id, actor_id)


def update_pcn(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    actor_id: Optional[int],
    data: dict,
) -> FleetPcn:
    pcn = get_or_create_pcn(db, hire_id, tenant_id, actor_id)
    user_name = actor_name_for(db, actor_id)

    for key, value in data.items():
        if not hasattr(pcn, key):
            continue
        old = getattr(pcn, key)
        if norm(old) == norm(value):
            continue
        db.add(FleetHireAudit(
            hire_id=hire_id,
            user=user_name,
            field_changed=f"pcn.{key}",
            old_value=norm(old),
            new_value=norm(value),
        ))
        setattr(pcn, key, value)

    pcn.updated_by = actor_id
    db.commit()
    db.refresh(pcn)
    return pcn


def add_pcn_document(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    actor_id: Optional[int],
    doc_type: str,
    file: UploadFile,
) -> FleetPcnDocument:
    pcn = get_or_create_pcn(db, hire_id, tenant_id, actor_id)
    result = S3Service().upload_task_attachment_with_fallback(file)
    user_name = actor_name_for(db, actor_id)

    doc = FleetPcnDocument(
        pcn_id=pcn.id,
        doc_type=doc_type,
        filename=getattr(file, "filename", None),
        s3_key=result.get("s3_key"),
        file_url=result.get("file_url"),
        storage_backend=result.get("storage_backend"),
        received_on=date.today(),
        created_by=actor_id,
        uploaded_by=user_name,
    )
    db.add(doc)
    db.add(FleetHireAudit(
        hire_id=hire_id,
        user=user_name,
        field_changed=f"pcn.document.{doc_type}",
        old_value="",
        new_value=getattr(file, "filename", "") or "",
    ))
    db.commit()
    db.refresh(doc)
    return doc


def list_pcn_documents(db: Session, hire_id: int, tenant_id: Optional[int]):
    pcn = get_or_create_pcn(db, hire_id, tenant_id)
    return (
        db.query(FleetPcnDocument)
        .filter(FleetPcnDocument.pcn_id == pcn.id)
        .order_by(FleetPcnDocument.id)
        .all()
    )


def delete_pcn_document(db: Session, hire_id: int, tenant_id: Optional[int], doc_id: int) -> dict:
    pcn = get_or_create_pcn(db, hire_id, tenant_id)
    doc = (
        db.query(FleetPcnDocument)
        .filter(FleetPcnDocument.id == doc_id, FleetPcnDocument.pcn_id == pcn.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="PCN document not found")
    db.delete(doc)
    db.commit()
    return {"success": True}


def add_pcn_note(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    actor_id: Optional[int],
    note_text: str,
) -> FleetPcnNote:
    note_text = (note_text or "").strip()
    if not note_text:
        raise HTTPException(status_code=400, detail="Note is required")

    pcn = get_or_create_pcn(db, hire_id, tenant_id, actor_id)
    user_name = actor_name_for(db, actor_id)

    note = FleetPcnNote(
        pcn_id=pcn.id,
        note=note_text,
        created_by=actor_id,
        created_by_name=user_name,
    )
    db.add(note)
    db.add(FleetHireAudit(
        hire_id=hire_id,
        user=user_name,
        field_changed="pcn.note",
        old_value="",
        new_value=note_text,
    ))
    db.commit()
    db.refresh(note)
    return note


def list_pcn_notes(db: Session, hire_id: int, tenant_id: Optional[int]):
    pcn = get_or_create_pcn(db, hire_id, tenant_id)
    return (
        db.query(FleetPcnNote)
        .filter(FleetPcnNote.pcn_id == pcn.id)
        .order_by(FleetPcnNote.id.desc())
        .all()
    )


def upsert_pcn_reminder(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    actor_id: Optional[int],
    reminder_type: str,
    data: dict,
) -> FleetPcnReminder:
    pcn = get_or_create_pcn(db, hire_id, tenant_id, actor_id)
    reminder = (
        db.query(FleetPcnReminder)
        .filter(FleetPcnReminder.pcn_id == pcn.id, FleetPcnReminder.reminder_type == reminder_type)
        .first()
    )
    if not reminder:
        reminder = FleetPcnReminder(pcn_id=pcn.id, reminder_type=reminder_type, created_by=actor_id)
        db.add(reminder)

    for key, value in data.items():
        if hasattr(reminder, key):
            setattr(reminder, key, value)

    db.commit()
    db.refresh(reminder)
    return reminder


def list_pcn_reminders(db: Session, hire_id: int, tenant_id: Optional[int]):
    pcn = get_or_create_pcn(db, hire_id, tenant_id)
    return (
        db.query(FleetPcnReminder)
        .filter(FleetPcnReminder.pcn_id == pcn.id)
        .order_by(FleetPcnReminder.id)
        .all()
    )
