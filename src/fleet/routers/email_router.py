from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.services import email_service
from fleet.services.common import get_hire_or_404

router = APIRouter()

# Attachment guard rails (defence against using this as a large-payload relay).
MAX_FILES = 10
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB per file
MAX_TOTAL_BYTES = 25 * 1024 * 1024  # 25 MB per email


@router.post("/hire/{hire_id}/email")
async def send_hire_email_route(
    hire_id: int,
    to: str = Form(...),
    subject: str = Form(""),
    body: str = Form(""),
    cc: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    get_hire_or_404(db, hire_id, tenant_id)
    if "@" not in (to or ""):
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Too many attachments (max {MAX_FILES}).")

    attachments = []
    total = 0
    for f in files:
        content = await f.read()
        if not content:
            continue
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail=f"{f.filename or 'Attachment'} exceeds the 15 MB limit.")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=400, detail="Attachments exceed the 25 MB total limit.")
        attachments.append(email_service.build_attachment(f.filename, f.content_type, content))

    result = email_service.send_hire_email(to=to, subject=subject, body=body, attachments=attachments, cc=cc)
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("detail") or "Email failed to send.")
    return result
