import base64
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from appflow.models.case_activity import CaseActivityItemOut, CaseActivityNoteOut
from appflow.services.case_activity_service import CaseActivityService
from appflow.services.microsoft_graph_token_service import MicrosoftGraphTokenService
from appflow.services.outlook_case_activity_service import OutlookCaseActivityService
from appflow.services.s3_service import S3Service
from appflow.utils import build_case_reference
from libdata.models.tables import CaseNote, CaseNoteReply, Claim, User
from libdata.settings import get_session

case_activity_router = APIRouter(prefix="/case-activity", tags=["Case Activity"])
def utc_now():
    return datetime.now(timezone.utc)


def _normalize_document_key(raw_key: str) -> str:
    value = (raw_key or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        value = parsed.path.lstrip("/")
    else:
        value = value.split("?", 1)[0].split("#", 1)[0]

    return unquote(value).lstrip("/")

def get_outlook_token(db: Session) -> str:
    return MicrosoftGraphTokenService.get_access_token("read")


def _current_user_id(request: Request) -> Optional[int]:
    value = getattr(request.state, "user_id", None)
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _user_display(db: Session, user_id: Optional[int]) -> Dict[str, str]:
    if not user_id:
        return {"name": "Unknown User", "role": "Claim Handler"}

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"name": "Unknown User", "role": "Claim Handler"}

    # Display name = the part of the user's email (user_name) before "@".
    un = getattr(user, "user_name", "") or ""
    name = un.split("@")[0] if "@" in un else (un or "Unknown User")
    return {
        "name": name,
        "role": getattr(user, "role", "Claim Handler") or "Claim Handler",
    }


def _pack_note_value(text: str, attachments: Optional[List[Dict[str, Any]]] = None) -> str:
    attachments = attachments or []
    if not attachments:
        return text or ""
    return json.dumps({"text": text or "", "attachments": attachments})


def _unpack_note_value(value: Any) -> Dict[str, Any]:
    if not value:
        return {"text": "", "attachments": []}
    if isinstance(value, dict):
        return {
            "text": value.get("text") or value.get("note") or value.get("reply") or "",
            "attachments": value.get("attachments") or [],
        }
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return {
                    "text": parsed.get("text") or parsed.get("note") or parsed.get("reply") or "",
                    "attachments": parsed.get("attachments") or [],
                }
        except Exception:
            pass
        return {"text": value, "attachments": []}
    return {"text": str(value), "attachments": []}


async def _upload_note_files(
    files: List[UploadFile],
    claim_id: int,
    category: str = "case-notes",
) -> List[Dict[str, Any]]:
    uploaded: List[Dict[str, Any]] = []
    if not files:
        return uploaded

    s3_service = S3Service()
    for file in files:
        if not file or not file.filename:
            continue
        result = s3_service.upload_case_document(file=file, claim_id=claim_id, category=category)
        uploaded.append({
            "file_name": file.filename,
            "file_url": result.get("file_url", ""),
            "s3_key": result.get("s3_key", ""),
            "file_size": "",
            "case_document_id": None,
            "content_type": file.content_type or "application/octet-stream",
        })
    return uploaded


def _with_presigned_attachment_urls(attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not attachments:
        return []
    s3_service = S3Service()
    output = []
    for attachment in attachments:
        item = dict(attachment)
        s3_key = item.get("s3_key")
        if s3_key:
            try:
                item["file_url"] = s3_service.generate_presigned_download_url(
                    s3_key=s3_key,
                    expires_in_seconds=3600,
                )
            except Exception as exc:
                print(f"[CaseActivity] Failed to presign note attachment: {exc}")
        output.append(item)
    return output


@case_activity_router.get("/claim/{claim_id}", response_model=List[CaseActivityItemOut])
def get_case_activity(claim_id: int, db: Session = Depends(get_session)):
    return CaseActivityService.get_case_activity(claim_id, db)


@case_activity_router.get("/all", response_model=List[CaseActivityItemOut])
def get_all_case_activity(
    include_emails: bool = Query(False),
    db: Session = Depends(get_session),
):
    claims = (
        db.query(Claim)
        .filter(Claim.is_deleted == False)
        .order_by(Claim.created_at.desc())
        .all()
    )

    items: List[CaseActivityItemOut] = []
    references: List[str] = []
    for claim in claims:
        try:
            ref = build_case_reference(claim.id, db)
        except Exception as exc:
            ref = ""
            print(f"[CaseActivity] Failed to build reference for claim {claim.id}: {exc}")
        if ref:
            references.append(ref)

        try:
            # Never do a per-claim Outlook search here — that was N Graph calls
            # (one reference per claim) and made this endpoint extremely slow.
            claim_items = CaseActivityService.get_case_activity(
                claim.id,
                db,
                include_emails=False,
            )
            # Tag each item with its claim reference so the all-cases view can
            # show which claim every activity belongs to.
            for it in claim_items:
                it.claim_reference = ref
            items.extend(claim_items)
        except Exception as exc:
            print(f"[CaseActivity] Failed to load activity for claim {claim.id}: {exc}")

    # Emails: ONE Graph call for the whole mailbox, then keep only emails whose
    # subject/body mentions a claim reference (Khalid-, Patel-, any) — not every
    # unrelated email, and not a slow per-claim search.
    if include_emails:
        try:
            token = get_outlook_token(db)
            if token:
                items.extend(
                    OutlookCaseActivityService.get_all_emails(
                        token, references=references, top=200
                    )
                )
        except Exception as exc:
            print(f"[CaseActivity] Failed to load all-mailbox emails: {exc}")

    items.sort(key=lambda item: item.timestamp.isoformat() if item.timestamp else "", reverse=True)
    return items


@case_activity_router.get("/manual-notes")
def get_manual_note_threads(
    claim_id: Optional[int] = Query(None),
    db: Session = Depends(get_session),
):
    """Standalone note threads created from the Notes tab (activity_ref like
    'manual-note-%'). These have no backing history activity, so the normal
    activity feed never surfaces them — this lets the Notes tab reload them.
    Grouped by activity_ref; each thread carries its claim reference."""
    q = (
        db.query(CaseNote)
        .filter(
            CaseNote.activity_ref.like("manual-note-%"),
            CaseNote.is_deleted == False,
        )
    )
    if claim_id:
        q = q.filter(CaseNote.claim_id == claim_id)
    notes = q.order_by(CaseNote.created_at.desc()).all()

    ref_cache: Dict[int, str] = {}
    threads: Dict[str, Dict[str, Any]] = {}
    for note in notes:
        ref = note.activity_ref
        if ref not in threads:
            cid = note.claim_id
            if cid not in ref_cache:
                try:
                    ref_cache[cid] = build_case_reference(cid, db)
                except Exception:
                    ref_cache[cid] = ""
            threads[ref] = {
                "activity_ref": ref,
                "claim_id": note.claim_id,
                "claim_reference": ref_cache[cid],
                "notes": [],
            }

        note_user = _user_display(db, note.created_by)
        note_value = _unpack_note_value(note.note)
        replies = (
            db.query(CaseNoteReply)
            .filter(CaseNoteReply.note_id == note.id, CaseNoteReply.is_deleted == False)
            .order_by(CaseNoteReply.created_at.asc())
            .all()
        )
        threads[ref]["notes"].append({
            "id": note.id,
            "activityId": note.activity_ref,
            "text": note_value["text"],
            "attachments": _with_presigned_attachment_urls(note_value["attachments"]),
            "createdAt": note.created_at,
            "createdById": note.created_by,
            "createdByName": note_user["name"],
            "createdByRole": note_user["role"],
            "replies": [
                {
                    "id": reply.id,
                    "noteId": note.id,
                    "text": (reply_value := _unpack_note_value(reply.reply))["text"],
                    "attachments": _with_presigned_attachment_urls(reply_value["attachments"]),
                    "createdAt": reply.created_at,
                    "createdById": reply.created_by,
                    "createdByName": (reply_user := _user_display(db, reply.created_by))["name"],
                    "createdByRole": reply_user["role"],
                }
                for reply in replies
            ],
        })

    return list(threads.values())


@case_activity_router.get("/document/presigned-url")
def get_case_activity_document_presigned_url(
    request: Request,
    s3_key: str = Query(...),
    download: bool = Query(False),
):
    s3_key = _normalize_document_key(s3_key)
    if not s3_key:
        raise HTTPException(status_code=400, detail="Document key is required")

    if S3Service.is_local_upload_key(s3_key):
        public_path = S3Service.local_upload_public_path(s3_key)
        return {"url": f"{str(request.base_url).rstrip('/')}{public_path}"}

    s3_service = S3Service()
    url = s3_service.generate_presigned_download_url(
        s3_key=s3_key,
        expires_in_seconds=3600,
        force_download=download,
    )
    return {"url": url}


@case_activity_router.get("/activities/{activity_id}/notes")
def get_activity_notes(activity_id: str, db: Session = Depends(get_session)):
    notes = (
        db.query(CaseNote)
        .filter(CaseNote.activity_ref == str(activity_id), CaseNote.is_deleted == False)
        .order_by(CaseNote.created_at.desc())
        .all()
    )

    result = []
    for note in notes:
        note_user = _user_display(db, note.created_by)
        note_value = _unpack_note_value(note.note)

        replies = (
            db.query(CaseNoteReply)
            .filter(CaseNoteReply.note_id == note.id, CaseNoteReply.is_deleted == False)
            .order_by(CaseNoteReply.created_at.asc())
            .all()
        )

        result.append({
            "id": note.id,
            "activityId": note.activity_ref,
            "text": note_value["text"],
            "attachments": _with_presigned_attachment_urls(note_value["attachments"]),
            "createdAt": note.created_at,
            "createdById": note.created_by,
            "createdByName": note_user["name"],
            "createdByRole": note_user["role"],
            "replies": [
                {
                    "id": reply.id,
                    "noteId": note.id,
                    "text": (reply_value := _unpack_note_value(reply.reply))["text"],
                    "attachments": _with_presigned_attachment_urls(reply_value["attachments"]),
                    "createdAt": reply.created_at,
                    "createdById": reply.created_by,
                    "createdByName": (reply_user := _user_display(db, reply.created_by))["name"],
                    "createdByRole": reply_user["role"],
                }
                for reply in replies
            ],
        })

    return result


@case_activity_router.post(
    "/claims/{claim_id}/activities/{activity_id}/notes",
    response_model=CaseActivityNoteOut,
)
async def create_case_note(
    claim_id: int,
    activity_id: str,
    request: Request,
    note: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
):
    user_id = _current_user_id(request)
    attachments = await _upload_note_files(files, claim_id, category="case-notes")
    print(activity_id)

    case_note = CaseNote(
        claim_id=claim_id,
        history_activity_id=None,
        note=_pack_note_value(note, attachments),
        activity_ref=str(activity_id),
        created_by=user_id,
        created_at=utc_now(),
    )

    db.add(case_note)
    db.commit()
    db.refresh(case_note)

    # Notify any @mentioned users (tagging in the note body).
    try:
        from appflow.services.notification_service import create_mention_notifications
        from appflow.utils import build_case_reference
        tenant_id = getattr(request.state, "tenant_id", None)
        try:
            case_ref = build_case_reference(claim_id, db)
        except Exception:
            case_ref = ""
        create_mention_notifications(
            db,
            note_text=note,
            claim_id=claim_id,
            actor_user_id=user_id,
            tenant_id=tenant_id,
            case_reference=case_ref,
        )
    except Exception:
        # Mention creation failed (e.g. the notifications table isn't migrated
        # yet). Roll back so the note response can still be built — the note
        # itself was already committed above.
        db.rollback()

    user = _user_display(db, user_id)
    unpacked = _unpack_note_value(case_note.note)
    return {
        "id": case_note.id,
        "activityId": activity_id,
        "text": unpacked["text"],
        "attachments": _with_presigned_attachment_urls(unpacked["attachments"]),
        "createdAt": case_note.created_at,
        "createdById": user_id,
        "createdByName": user["name"],
        "createdByRole": user["role"],
        "replies": [],
    }


@case_activity_router.post("/notes/{note_id}/reply")
async def create_note_reply(
    note_id: int,
    request: Request,
    reply: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
):
    parent_note = (
        db.query(CaseNote)
        .filter(CaseNote.id == note_id, CaseNote.is_deleted == False)
        .first()
    )
    if not parent_note:
        raise HTTPException(status_code=404, detail="Note not found")

    user_id = _current_user_id(request)
    attachments = await _upload_note_files(files, parent_note.claim_id, category="case-note-replies")

    note_reply = CaseNoteReply(
        note_id=note_id,
        reply=_pack_note_value(reply, attachments),
        created_by=user_id,
        created_at=utc_now(),
    )

    db.add(note_reply)
    db.commit()
    db.refresh(note_reply)

    # (#7) Notify the original commenter + any @mentions in the reply.
    try:
        from appflow.services.notification_service import safe_notify, create_mention_notifications
        from appflow.utils import build_case_reference
        tenant_id = getattr(request.state, "tenant_id", None)
        try:
            ref = build_case_reference(parent_note.claim_id, db)
        except Exception:
            ref = ""
        actor_name = _user_display(db, user_id)["name"]
        if parent_note.created_by and parent_note.created_by != user_id:
            snippet = (reply or "").strip().replace("\n", " ")
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            safe_notify(
                db, recipient_user_id=parent_note.created_by, tenant_id=tenant_id, actor_user_id=user_id,
                category="Mention", tab="Mentions", title="New reply to your comment",
                description=f"{actor_name} replied to your comment{(' in ' + ref) if ref else ''}: {snippet}",
                claim_id=parent_note.claim_id, email=True,
            )
        create_mention_notifications(
            db, note_text=reply, claim_id=parent_note.claim_id,
            actor_user_id=user_id, tenant_id=tenant_id, case_reference=ref,
        )
    except Exception:
        db.rollback()

    user = _user_display(db, user_id)
    unpacked = _unpack_note_value(note_reply.reply)
    return {
        "id": note_reply.id,
        "noteId": note_id,
        "text": unpacked["text"],
        "attachments": _with_presigned_attachment_urls(unpacked["attachments"]),
        "createdAt": note_reply.created_at,
        "createdById": user_id,
        "createdByName": user["name"],
        "createdByRole": user["role"],
    }


@case_activity_router.put("/notes/{note_id}")
async def update_note(
    note_id: int,
    request: Request,
    note: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
):
    case_note = (
        db.query(CaseNote)
        .filter(CaseNote.id == note_id, CaseNote.is_deleted == False)
        .first()
    )
    if not case_note:
        raise HTTPException(status_code=404, detail="Note not found")

    current_user_id = _current_user_id(request)
    if current_user_id and case_note.created_by and str(case_note.created_by) != str(current_user_id):
        raise HTTPException(status_code=403, detail="You can only edit your own note")

    existing = _unpack_note_value(case_note.note)
    new_attachments = await _upload_note_files(files, case_note.claim_id, category="case-notes")
    case_note.note = _pack_note_value(note, existing["attachments"] + new_attachments)

    db.commit()
    db.refresh(case_note)

    user = _user_display(db, case_note.created_by)
    unpacked = _unpack_note_value(case_note.note)
    return {
        "id": case_note.id,
        "activityId": case_note.activity_ref,
        "text": unpacked["text"],
        "attachments": _with_presigned_attachment_urls(unpacked["attachments"]),
        "createdAt": case_note.created_at,
        "createdById": case_note.created_by,
        "createdByName": user["name"],
        "createdByRole": user["role"],
        "replies": [],
    }


@case_activity_router.put("/note-replies/{reply_id}")
async def update_note_reply(
    reply_id: int,
    request: Request,
    reply: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
):
    note_reply = (
        db.query(CaseNoteReply)
        .filter(CaseNoteReply.id == reply_id, CaseNoteReply.is_deleted == False)
        .first()
    )
    if not note_reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    current_user_id = _current_user_id(request)
    if current_user_id and note_reply.created_by and str(note_reply.created_by) != str(current_user_id):
        raise HTTPException(status_code=403, detail="You can only edit your own reply")

    parent_note = db.query(CaseNote).filter(CaseNote.id == note_reply.note_id).first()
    if not parent_note:
        raise HTTPException(status_code=404, detail="Parent note not found")

    existing = _unpack_note_value(note_reply.reply)
    new_attachments = await _upload_note_files(files, parent_note.claim_id, category="case-note-replies")
    note_reply.reply = _pack_note_value(reply, existing["attachments"] + new_attachments)

    db.commit()
    db.refresh(note_reply)

    user = _user_display(db, note_reply.created_by)
    unpacked = _unpack_note_value(note_reply.reply)
    return {
        "id": note_reply.id,
        "noteId": note_reply.note_id,
        "text": unpacked["text"],
        "attachments": _with_presigned_attachment_urls(unpacked["attachments"]),
        "createdAt": note_reply.created_at,
        "createdById": note_reply.created_by,
        "createdByName": user["name"],
        "createdByRole": user["role"],
    }


@case_activity_router.delete("/notes/{note_id}")
def delete_note(note_id: int, request: Request, db: Session = Depends(get_session)):
    note = db.query(CaseNote).filter(CaseNote.id == note_id, CaseNote.is_deleted == False).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    current_user_id = _current_user_id(request)
    if current_user_id and note.created_by and str(note.created_by) != str(current_user_id):
        raise HTTPException(status_code=403, detail="You can only delete your own note")

    note.is_deleted = True
    db.commit()
    return {"message": "Note deleted successfully"}


@case_activity_router.delete("/note-replies/{reply_id}")
def delete_note_reply(reply_id: int, request: Request, db: Session = Depends(get_session)):
    reply = db.query(CaseNoteReply).filter(CaseNoteReply.id == reply_id, CaseNoteReply.is_deleted == False).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    current_user_id = _current_user_id(request)
    if current_user_id and reply.created_by and str(reply.created_by) != str(current_user_id):
        raise HTTPException(status_code=403, detail="You can only delete your own reply")

    reply.is_deleted = True
    db.commit()
    return {"message": "Reply deleted successfully"}


@case_activity_router.post("/email/reply-with-attachments")
async def reply_to_email_with_attachments(
    message_id: str = Form(...),
    comment: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
):
    token = get_outlook_token(db)
    if not token:
        raise HTTPException(status_code=400, detail="Outlook token not configured")

    attachments = []
    for file in files:
        content = await file.read()
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": file.filename,
            "contentType": file.content_type or "application/octet-stream",
            "contentBytes": base64.b64encode(content).decode("utf-8"),
        })

    success = OutlookCaseActivityService.reply_with_attachments_via_graph(
        message_id=message_id,
        comment=comment,
        attachments=attachments,
        access_token=token,
    )
    if not success:
        raise HTTPException(status_code=502, detail="Graph API reply with attachments failed")
    return {"status": "sent"}


class EmailForwardRequest(BaseModel):
    message_id: str
    subject: str
    body_text: str = ""
    to_email: str = ""
    comment: str = ""
    attachment_names: List[str] = []
    use_graph: bool = False


@case_activity_router.post("/email/forward-with-attachments")
async def forward_email_with_attachments(
    message_id: str = Form(None),
    to_email: str = Form(...),
    comment: str = Form(""),
    subject: str = Form(""),
    attachment_urls: str = Form("[]"),
    is_html: str = Form("false"),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
):
    token = get_outlook_token(db)
    if not token:
        raise HTTPException(status_code=400, detail="Outlook token not configured")

    attachments = []
    for file in files:
        content = await file.read()
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": file.filename,
            "contentType": file.content_type or "application/octet-stream",
            "contentBytes": base64.b64encode(content).decode("utf-8"),
        })

    html_mode = str(is_html).lower() == "true"
    try:
        url_attachments = json.loads(attachment_urls or "[]")
    except Exception:
        url_attachments = []

    button_items = []
    if url_attachments:
        s3_service = S3Service()
        for item in url_attachments:
            file_url = (item or {}).get("file_url")
            file_name = (item or {}).get("file_name") or "attachment.pdf"
            activity_type = ((item or {}).get("activity_type") or "").lower()
            if not file_url:
                continue
            try:
                s3_key = file_url.split(".amazonaws.com/")[-1].split("?")[0]
                presigned_url = s3_service.generate_presigned_download_url(s3_key=s3_key, expires_in_seconds=3600)
                button_items.append({"file_name": file_name, "file_url": presigned_url, "activity_type": activity_type})
            except Exception as exc:
                print(f"[CaseActivity] Failed to prepare presigned button link: {exc}")

    pdf_buttons_html = ""
    if button_items:
        html_mode = True
        pdf_buttons_html = "<div style='margin-top:24px;text-align:center;'>"
        for item in button_items:
            file_name_lower = (item.get("file_name") or "").lower()
            activity_type = (item.get("activity_type") or "").lower()
            if "witness" in activity_type or "witness" in file_name_lower:
                label = "View Witness Form"
            elif "ai" in activity_type or "ai" in file_name_lower or "damage" in file_name_lower or "report" in file_name_lower:
                label = "View AI Report"
            else:
                label = "View PDF"
            pdf_buttons_html += f"""
                <a href="{item['file_url']}" target="_blank"
                   style="display:inline-block;margin:6px;padding:14px 28px;background:#245BDB;color:#ffffff;text-decoration:none;border-radius:6px;font-family:Arial,sans-serif;font-size:14px;font-weight:500;">
                   {label}
                </a>
            """
        pdf_buttons_html += "</div>"

    final_comment = (comment or "") + pdf_buttons_html
    is_real_message = message_id and str(message_id).lower() not in {"none", "null", ""}
    final_subject = subject or "Case Activity"

    if not is_real_message:
        success = OutlookCaseActivityService.send_email_with_attachments_via_graph(
            to_email=to_email,
            subject=final_subject,
            comment=final_comment,
            attachments=attachments,
            access_token=token,
            is_html=html_mode,
        )
    else:
        success = OutlookCaseActivityService.forward_with_attachments_via_graph(
            message_id=message_id,
            to_email=to_email,
            comment=final_comment,
            attachments=attachments,
            access_token=token,
            is_html=html_mode,
            subject=final_subject,
        )

    if not success:
        raise HTTPException(status_code=502, detail="Graph API forward with attachments failed")
    return {"status": "sent"}


@case_activity_router.get("/email-attachment/{message_id}/{attachment_id}")
def download_email_attachment(message_id: str, attachment_id: str, db: Session = Depends(get_session)):
    token = get_outlook_token(db)
    if not token:
        raise HTTPException(status_code=400, detail="Outlook token not configured")

    result = OutlookCaseActivityService.get_attachment_bytes(
        message_id=message_id,
        attachment_id=attachment_id,
        access_token=token,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Attachment not found")

    raw_bytes, filename, content_type = result
    return Response(
        content=raw_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(raw_bytes)),
        },
    )
