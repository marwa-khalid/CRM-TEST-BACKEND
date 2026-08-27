"""Case History section endpoints — the History screen opened from a claim.
List (with search + filters), record detail, filter options, and create. All
records are always scoped to the claim they were created under."""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from libdata.settings import get_session
from appflow.models.case_history import (
    CaseHistoryCorrespondent,
    CaseHistoryCreate,
    CaseHistoryFilterOptions,
    CaseHistoryOut,
)
from appflow.services.case_history_service import CaseHistoryService, _ACTION_BY_VALUE
from appflow.utils import actor_id

case_history_router = APIRouter(prefix="/case-history", tags=["Case History"])

# Owners a History record can attach to. 'claim' is the claims side; the rest are
# the self-contained Fleet module (fleet hires + VM CAMS / VM Skyline vehicles).
_ALLOWED_SCOPES = {"claim", "fleet_hire", "vm_cams", "vm_skyline"}


def _check_scope(scope_type: str) -> None:
    if scope_type not in _ALLOWED_SCOPES:
        raise HTTPException(status_code=400, detail=f"Unknown scope_type: {scope_type!r}")


def _parse_dt(v: Optional[str]):
    from datetime import datetime
    if not v:
        return None
    try:
        return datetime.fromisoformat(v[:19]) if len(v) > 10 else datetime.fromisoformat(v[:10])
    except ValueError:
        return None


@case_history_router.get("/claim/{claim_id}", response_model=List[CaseHistoryOut])
def list_case_history(
    claim_id: int,
    search: Optional[str] = Query(None, description="Free-text match on details/subject/correspondent/handler"),
    action_type: Optional[List[str]] = Query(None, description="Filter by one or more action types"),
    correspondent: Optional[List[str]] = Query(None),
    handler: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None, description="Inclusive start date/datetime (ISO)"),
    date_to: Optional[str] = Query(None, description="Inclusive end date/datetime (ISO)"),
    db: Session = Depends(get_session),
):
    """Chronological History for a claim, newest first, with optional filters."""
    from datetime import datetime

    def _parse(v: Optional[str]):
        if not v:
            return None
        try:
            return datetime.fromisoformat(v[:19]) if len(v) > 10 else datetime.fromisoformat(v[:10])
        except ValueError:
            return None

    return CaseHistoryService.list_for_claim(
        db,
        claim_id,
        search=search,
        action_type=action_type,
        correspondent=correspondent,
        handler=handler,
        date_from=_parse(date_from),
        date_to=_parse(date_to),
    )


@case_history_router.get("/claim/{claim_id}/filters", response_model=CaseHistoryFilterOptions)
def case_history_filter_options(claim_id: int, db: Session = Depends(get_session)):
    """Distinct correspondents / handlers / action types present in the claim's
    history — feeds the History screen's filter dropdowns."""
    return CaseHistoryService.filter_options(db, claim_id)


@case_history_router.get("/claim/{claim_id}/correspondents", response_model=List[CaseHistoryCorrespondent])
def case_history_correspondents(claim_id: int, db: Session = Depends(get_session)):
    """Third-party email addresses on the claim — feeds the Correspondent dropdown
    and the outgoing-call phone auto-fill."""
    return CaseHistoryService.correspondents(db, claim_id)


@case_history_router.post("/claim/{claim_id}/import-email", response_model=CaseHistoryOut)
async def import_email_into_history(
    claim_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    current_user: Optional[int] = Depends(actor_id),
):
    """Import a dragged-in Outlook email (.eml / .msg) as a Send Email History record."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        return CaseHistoryService.import_email(db, claim_id, file.filename or "email.eml", data, current_user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not import email: {exc}")


@case_history_router.post("/claim/{claim_id}/log-document", response_model=CaseHistoryOut)
async def log_document_into_history(
    claim_id: int,
    file: UploadFile = File(...),
    details: str = Form(...),
    action_type: str = Form("send_letter"),
    subject: Optional[str] = Form(None),
    correspondent: Optional[str] = Form(None),
    source: str = Form("document"),
    db: Session = Depends(get_session),
    current_user: Optional[int] = Depends(actor_id),
):
    """Log a downloaded/generated document (e.g. a Payment Pack PDF → SL, an
    engineer letter → SE) as a Case History record, storing the file so it's
    viewable in the detail pane."""
    action = _ACTION_BY_VALUE.get((action_type or "").strip().lower())
    if action is None:
        raise HTTPException(status_code=400, detail=f"Invalid action_type: {action_type!r}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        return CaseHistoryService.log_document_record(
            db,
            claim_id,
            action_type=action,
            subject=subject,
            details=details,
            correspondent=correspondent,
            documents=[{
                "name": file.filename or "document",
                "data": data,
                "content_type": file.content_type or "application/octet-stream",
            }],
            source=source,
            current_user=current_user,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not log document: {exc}")


# ── Fleet / generic scope endpoints (fleet_hire, vm_cams, vm_skyline) ─────────
@case_history_router.get("/scope/{scope_type}/{scope_id}", response_model=List[CaseHistoryOut])
def list_scope_history(
    scope_type: str,
    scope_id: int,
    search: Optional[str] = Query(None),
    action_type: Optional[List[str]] = Query(None),
    correspondent: Optional[List[str]] = Query(None),
    handler: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """History for any owner (fleet hire / VM vehicle), newest first."""
    _check_scope(scope_type)
    return CaseHistoryService.list_for_scope(
        db, scope_type, scope_id,
        search=search, action_type=action_type, correspondent=correspondent,
        handler=handler, date_from=_parse_dt(date_from), date_to=_parse_dt(date_to),
    )


@case_history_router.get("/scope/{scope_type}/{scope_id}/filters", response_model=CaseHistoryFilterOptions)
def scope_filter_options(scope_type: str, scope_id: int, db: Session = Depends(get_session)):
    _check_scope(scope_type)
    return CaseHistoryService.filter_options_for_scope(db, scope_type, scope_id)


@case_history_router.get("/scope/{scope_type}/{scope_id}/correspondents")
def scope_correspondents(scope_type: str, scope_id: int, db: Session = Depends(get_session)):
    """Correspondent options for the History correspondent field: for VM-CAMS, the
    linked claim's client email (default) + Third Party emails."""
    _check_scope(scope_type)
    return CaseHistoryService.scope_correspondents(db, scope_type, scope_id)


@case_history_router.get("/scope/{scope_type}/{scope_id}/emails")
def scope_emails(
    scope_type: str,
    scope_id: int,
    reference: Optional[str] = Query(None, description="Explicit mailbox reference to match (e.g. a vehicle reg like OV66HFF). Fleet passes the registration number so emails mentioning it surface here."),
    db: Session = Depends(get_session),
):
    """Mailbox emails matching this owner's reference (shared mailbox). Fleet/VM pass
    the vehicle registration as `reference`; otherwise a synthetic scope reference
    is used."""
    _check_scope(scope_type)
    ref = (reference or "").strip()
    if ref:
        return CaseHistoryService.emails_by_reference(db, ref, scope_type=scope_type, scope_id=scope_id)
    return CaseHistoryService.scope_emails(db, scope_type, scope_id)


@case_history_router.post("/scope/{scope_type}/{scope_id}", response_model=CaseHistoryOut)
def create_scope_history(
    scope_type: str,
    scope_id: int,
    payload: CaseHistoryCreate,
    db: Session = Depends(get_session),
    current_user: Optional[int] = Depends(actor_id),
):
    _check_scope(scope_type)
    try:
        return CaseHistoryService.create_for_scope(db, scope_type, scope_id, payload, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@case_history_router.post("/scope/{scope_type}/{scope_id}/import-email", response_model=CaseHistoryOut)
async def import_email_into_scope(
    scope_type: str,
    scope_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    current_user: Optional[int] = Depends(actor_id),
):
    """Import a dragged-in Outlook email as an Incoming Email (IE) record."""
    _check_scope(scope_type)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        return CaseHistoryService.import_email(
            db, scope_id, file.filename or "email.eml", data, current_user,
            scope_type=scope_type, scope_id=scope_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not import email: {exc}")


@case_history_router.post("/scope/{scope_type}/{scope_id}/log-document", response_model=CaseHistoryOut)
async def log_document_into_scope(
    scope_type: str,
    scope_id: int,
    file: UploadFile = File(...),
    details: str = Form(...),
    action_type: str = Form("send_letter"),
    subject: Optional[str] = Form(None),
    correspondent: Optional[str] = Form(None),
    handler: Optional[str] = Form(None),
    source: str = Form("document"),
    db: Session = Depends(get_session),
    current_user: Optional[int] = Depends(actor_id),
):
    """Log a generated/downloaded document (e.g. a hire Agreement → SL) as a Case
    History record for a fleet hire / VM vehicle, storing the file for preview."""
    _check_scope(scope_type)
    action = _ACTION_BY_VALUE.get((action_type or "").strip().lower())
    if action is None:
        raise HTTPException(status_code=400, detail=f"Invalid action_type: {action_type!r}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        return CaseHistoryService.log_document_record(
            db, scope_id,
            action_type=action,
            subject=subject,
            details=details,
            correspondent=correspondent,
            handler=handler,
            documents=[{"name": file.filename or "document", "data": data, "content_type": file.content_type or "application/octet-stream"}],
            source=source,
            current_user=current_user,
            scope_type=scope_type,
            scope_id=scope_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not log document: {exc}")


@case_history_router.get("/{record_id}/attachment/{index}/pages")
def history_attachment_preview_pages(record_id: int, index: int, db: Session = Depends(get_session)):
    """Render a stored attachment as page images (PDF → PNG per page) so the detail
    pane can preview the document like the Document Library, without a PDF viewer."""
    return CaseHistoryService.attachment_preview_pages(db, record_id, index)


@case_history_router.get("/{record_id}/attachment/{index}")
def download_history_attachment(record_id: int, index: int, db: Session = Depends(get_session)):
    """Stream a stored (imported-email) record's Nth attachment."""
    result = CaseHistoryService.attachment_bytes(db, record_id, index)
    if not result:
        raise HTTPException(status_code=404, detail="Attachment not found")
    raw, filename, content_type = result
    return Response(
        content=raw,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@case_history_router.get("/claim/{claim_id}/emails")
def case_history_emails(claim_id: int, db: Session = Depends(get_session)):
    """Case-referenced emails from the configured Outlook mailbox, shaped as
    read-only History records (with attachments in the payload)."""
    return CaseHistoryService.claim_emails(db, claim_id)


@case_history_router.get("/{record_id}", response_model=CaseHistoryOut)
def get_case_history_record(record_id: int, db: Session = Depends(get_session)):
    """Single History record — powers the Record Detail preview pane."""
    rec = CaseHistoryService.get_by_id(db, record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="History record not found")
    return rec


@case_history_router.post("/claim/{claim_id}", response_model=CaseHistoryOut)
def create_case_history_record(
    claim_id: int,
    payload: CaseHistoryCreate,
    db: Session = Depends(get_session),
    current_user: Optional[int] = Depends(actor_id),
):
    """Create a History record for the claim (Send Letter / Send Email / Incoming
    Call / Outgoing Call / Note / Diary)."""
    try:
        return CaseHistoryService.create(db, claim_id, payload, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
