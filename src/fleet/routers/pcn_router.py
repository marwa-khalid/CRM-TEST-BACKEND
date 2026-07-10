from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import actor_id, get_session, get_tenant_id
from fleet.models.schemas import (
    PcnDocumentResponse,
    PcnNoteCreate,
    PcnNoteResponse,
    PcnReminderResponse,
    PcnReminderUpdate,
    PcnResponse,
    PcnUpdate,
)
from fleet.services import pcn_service

router = APIRouter()


@router.get("/hire/{hire_id}/pcn", response_model=PcnResponse)
def get_pcn_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return pcn_service.get_pcn(db, hire_id, tenant_id, actor)


@router.patch("/hire/{hire_id}/pcn", response_model=PcnResponse)
def update_pcn_route(
    hire_id: int,
    payload: PcnUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return pcn_service.update_pcn(db, hire_id, tenant_id, actor, payload.model_dump(exclude_unset=True))


@router.post("/hire/{hire_id}/pcn/documents", response_model=PcnDocumentResponse)
def add_pcn_document_route(
    hire_id: int,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return pcn_service.add_pcn_document(db, hire_id, tenant_id, actor, doc_type, file)


@router.get("/hire/{hire_id}/pcn/documents", response_model=List[PcnDocumentResponse])
def list_pcn_documents_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return pcn_service.list_pcn_documents(db, hire_id, tenant_id)


@router.delete("/hire/{hire_id}/pcn/documents/{doc_id}")
def delete_pcn_document_route(
    hire_id: int,
    doc_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return pcn_service.delete_pcn_document(db, hire_id, tenant_id, doc_id)


@router.post("/hire/{hire_id}/pcn/notes", response_model=PcnNoteResponse)
def add_pcn_note_route(
    hire_id: int,
    payload: PcnNoteCreate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return pcn_service.add_pcn_note(db, hire_id, tenant_id, actor, payload.note)


@router.get("/hire/{hire_id}/pcn/notes", response_model=List[PcnNoteResponse])
def list_pcn_notes_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return pcn_service.list_pcn_notes(db, hire_id, tenant_id)


@router.put("/hire/{hire_id}/pcn/reminders/{reminder_type}", response_model=PcnReminderResponse)
def upsert_pcn_reminder_route(
    hire_id: int,
    reminder_type: str,
    payload: PcnReminderUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return pcn_service.upsert_pcn_reminder(
        db,
        hire_id,
        tenant_id,
        actor,
        reminder_type,
        payload.model_dump(exclude_unset=True),
    )


@router.get("/hire/{hire_id}/pcn/reminders", response_model=List[PcnReminderResponse])
def list_pcn_reminders_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return pcn_service.list_pcn_reminders(db, hire_id, tenant_id)
