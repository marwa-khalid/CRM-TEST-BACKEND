"""Case History service — chronological log of user-recorded case activities
(letters, emails, calls, notes, diary). Backs the History screen: list (with
search + filters), record detail, and create. Kept separate from the file-based
Case Activity (HistoryActivities)."""
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from libdata.enums import CaseHistoryActionType
from libdata.models.tables import (
    CaseHistory,
    Claim,
    ThirdPartyInsurer,
    ClientDetail,
    Address,
    User,
)
from appflow.services.microsoft_graph_token_service import MicrosoftGraphTokenService
from appflow.services.outlook_case_activity_service import OutlookCaseActivityService
from appflow.services.s3_service import S3Service
from appflow.services.case_email_import import parse_email_bytes
from appflow.utils import build_case_reference


def _fmt_size(num: int) -> str:
    size = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"

# wire value ("send_letter") -> enum member
_ACTION_BY_VALUE = {a.value: a for a in CaseHistoryActionType}


def _to_dict(r: CaseHistory) -> dict:
    payload = r.payload
    # Give stored (imported-email) attachments an openable URL routed through the
    # record — the S3 key stays server-side.
    if isinstance(payload, dict) and isinstance(payload.get("attachments"), list):
        atts = []
        for i, a in enumerate(payload["attachments"]):
            a = dict(a or {})
            if a.get("s3_key") and not a.get("url"):
                a["url"] = f"/case-history/{r.id}/attachment/{i}"
            atts.append(a)
        payload = {**payload, "attachments": atts}
    return {
        "id": r.id,
        "claim_id": r.claim_id,
        "scope_type": r.scope_type,
        "scope_id": r.scope_id,
        "action_type": r.action_type.value if r.action_type else None,
        "posted_at": r.posted_at,
        "correspondent": r.correspondent,
        "handler": r.handler,
        "subject": r.subject,
        "details": r.details,
        "payload": payload,
        "created_by": r.created_by,
        "created_at": r.created_at,
    }


def _scope_clause(scope_type: str, scope_id: int):
    """SQLAlchemy filter selecting one owner's records. Claim records also carry
    claim_id, but every row now has scope_type/scope_id, so this works for both."""
    return and_(CaseHistory.scope_type == scope_type, CaseHistory.scope_id == scope_id)


class CaseHistoryService:
    @staticmethod
    def _list(
        db: Session,
        scope_type: str,
        scope_id: int,
        *,
        search: Optional[str] = None,
        action_type: Optional[List[str]] = None,
        correspondent: Optional[List[str]] = None,
        handler: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[dict]:
        q = db.query(CaseHistory).filter(
            _scope_clause(scope_type, scope_id),
            CaseHistory.is_deleted.isnot(True),
        )
        if action_type:
            members = [_ACTION_BY_VALUE[a] for a in action_type if a in _ACTION_BY_VALUE]
            if members:
                q = q.filter(CaseHistory.action_type.in_(members))
        if correspondent:
            q = q.filter(CaseHistory.correspondent.in_(correspondent))
        if handler:
            q = q.filter(CaseHistory.handler.in_(handler))
        if date_from:
            q = q.filter(CaseHistory.posted_at >= date_from)
        if date_to:
            # `date_to` is an inclusive end-of-day boundary.
            q = q.filter(CaseHistory.posted_at < date_to + timedelta(days=1))
        if search and search.strip():
            like = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    CaseHistory.details.ilike(like),
                    CaseHistory.subject.ilike(like),
                    CaseHistory.correspondent.ilike(like),
                    CaseHistory.handler.ilike(like),
                )
            )
        # Newest first (chronological, most recent at the top).
        q = q.order_by(CaseHistory.posted_at.desc().nullslast(), CaseHistory.id.desc())
        return [_to_dict(r) for r in q.all()]

    @staticmethod
    def list_for_claim(db: Session, claim_id: int, **kw) -> List[dict]:
        return CaseHistoryService._list(db, "claim", claim_id, **kw)

    @staticmethod
    def list_for_scope(db: Session, scope_type: str, scope_id: int, **kw) -> List[dict]:
        return CaseHistoryService._list(db, scope_type, scope_id, **kw)

    @staticmethod
    def get_by_id(db: Session, record_id: int) -> Optional[dict]:
        r = (
            db.query(CaseHistory)
            .filter(CaseHistory.id == record_id, CaseHistory.is_deleted.isnot(True))
            .first()
        )
        return _to_dict(r) if r else None

    @staticmethod
    def create(db: Session, claim_id: int, data, current_user: Optional[int]) -> dict:
        return CaseHistoryService.create_for_scope(
            db, "claim", claim_id, data, current_user,
            tenant_id=db.query(Claim.tenant_id).filter(Claim.id == claim_id).scalar(),
        )

    @staticmethod
    def create_for_scope(
        db: Session,
        scope_type: str,
        scope_id: int,
        data,
        current_user: Optional[int],
        *,
        tenant_id: Optional[int] = None,
    ) -> dict:
        action = _ACTION_BY_VALUE.get((data.action_type or "").strip().lower())
        if action is None:
            raise ValueError(f"Invalid action_type: {data.action_type!r}")
        rec = CaseHistory(
            claim_id=scope_id if scope_type == "claim" else None,
            scope_type=scope_type,
            scope_id=scope_id,
            tenant_id=tenant_id,
            action_type=action,
            posted_at=data.posted_at or datetime.utcnow(),
            correspondent=data.correspondent,
            handler=data.handler,
            subject=data.subject,
            details=data.details,
            payload=data.payload,
            created_by=current_user,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)

    @staticmethod
    def log_document_record(
        db: Session,
        claim_id: int,
        *,
        action_type: CaseHistoryActionType,
        subject: Optional[str] = None,
        details: Optional[str] = None,
        correspondent: Optional[str] = None,
        handler: Optional[str] = None,
        body_html: Optional[str] = None,
        documents: Optional[List[dict]] = None,   # [{name, data: bytes, content_type}]
        message_id: Optional[str] = None,
        source: str = "email",
        current_user: Optional[int] = None,
        posted_at: Optional[datetime] = None,
        scope_type: str = "claim",
        scope_id: Optional[int] = None,
    ) -> dict:
        """Log a Case History record for a system action (engineer instruct email →
        SE, payment-pack download → SL, generated hire document → SL, …). Any
        documents are stored in S3 and surfaced as openable attachments in the detail
        pane. Best-effort upload — the record is still written if S3 fails."""
        if scope_id is None:
            scope_id = claim_id
        is_claim = scope_type == "claim"

        claim_row = db.query(Claim).filter(Claim.id == scope_id).first() if is_claim else None
        tenant_id = claim_row.tenant_id if claim_row else None

        # Claim scope only: auto-fill handler (General Details handler) + correspondent
        # (the claim's third-party insurer) when the caller didn't supply them.
        if is_claim:
            if handler is None and claim_row is not None:
                h = getattr(claim_row, "handler", None)
                handler = (getattr(h, "label", "") or "") or None
            if correspondent is None:
                correspondent = CaseHistoryService._claim_tpi_correspondent(db, scope_id)

        att_refs: List[dict] = []
        docs = [d for d in (documents or []) if d.get("data")]
        if docs:
            s3 = S3Service()
            for doc in docs:
                name = doc.get("name") or "document"
                blob = doc.get("data") or b""
                key = f"history/{scope_type}/{scope_id}/docs/{uuid.uuid4().hex}_{name}"
                try:
                    s3.client.put_object(
                        Bucket=s3.bucket_name,
                        Key=key,
                        Body=blob,
                        ContentType=doc.get("content_type") or "application/octet-stream",
                    )
                    att_refs.append({"name": name, "size": _fmt_size(len(blob)), "s3_key": key})
                except Exception as exc:
                    print(f"[CaseHistoryService] document upload failed: {exc}")
                    att_refs.append({"name": name, "size": _fmt_size(len(blob))})

        rec = CaseHistory(
            claim_id=scope_id if is_claim else None,
            scope_type=scope_type,
            scope_id=scope_id,
            tenant_id=tenant_id,
            action_type=action_type,
            posted_at=posted_at or datetime.utcnow(),
            correspondent=correspondent,
            handler=handler,
            subject=subject,
            details=details,
            payload={
                "source": source,
                "message_id": message_id or None,
                "body_html": body_html or "",
                "body_text": "",
                "attachments": att_refs,
            },
            created_by=current_user,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)

    @staticmethod
    def correspondents(db: Session, claim_id: int) -> List[dict]:
        """ALL third-party email addresses in the tenant (from every claim's Third
        Party Insurer screen) — each with its name + phone, for the History forms'
        Correspondent dropdown and the outgoing-call phone auto-fill. Scoped to the
        given claim's tenant; only entries that actually have an email are returned."""
        tenant_id = db.query(Claim.tenant_id).filter(Claim.id == claim_id).scalar()

        # Every Third Party Insurer record in the tenant (join Claim for scoping).
        q = (
            db.query(ThirdPartyInsurer)
            .join(Claim, Claim.id == ThirdPartyInsurer.claim_id)
            .filter(ThirdPartyInsurer.is_deleted.isnot(True), Claim.is_deleted.isnot(True))
        )
        if tenant_id is not None:
            q = q.filter(Claim.tenant_id == tenant_id)
        tpis = q.all()

        client_ids = set()
        direct_emails: List[str] = []
        for tpi in tpis:
            for cid in (tpi.third_party_id, tpi.third_party_insurer_id, tpi.third_party_handling_id):
                if cid:
                    client_ids.add(cid)
            if (tpi.direct_email or "").strip():
                direct_emails.append(tpi.direct_email.strip())

        out: List[dict] = []
        if client_ids:
            rows = (
                db.query(ClientDetail, Address)
                .outerjoin(Address, Address.id == ClientDetail.address_id)
                .filter(ClientDetail.id.in_(client_ids))
                .all()
            )
            for cd, addr in rows:
                email = (addr.email or "").strip() if addr and addr.email else None
                if not email:
                    continue
                name = " ".join(x for x in [cd.first_name, cd.surname] if x).strip() or None
                phone = (addr.mobile_tel or addr.landline_tel or addr.home_tel or "").strip() or None if addr else None
                role = getattr(cd.role, "value", None) or (cd.role if isinstance(cd.role, str) else None) or "Third Party"
                out.append({"role": role, "name": name, "email": email, "phone": phone})
        for de in direct_emails:
            out.append({"role": "Direct Email", "name": None, "email": de, "phone": None})

        # Only correspondents with an email, de-duplicated by email, alphabetical.
        seen, result = set(), []
        for c in sorted(out, key=lambda x: (x["email"] or "").lower()):
            e = c.get("email")
            if e and e.lower() not in seen:
                seen.add(e.lower())
                result.append(c)
        return result

    @staticmethod
    def _claim_tpi_correspondent(db: Session, claim_id: int) -> Optional[str]:
        """The claim's third-party insurer, as a display name — used as the
        correspondent on payment-pack / letter records. Prefers the insurer party's
        name, then its email, then any direct email on the TPI row."""
        tpi = (
            db.query(ThirdPartyInsurer)
            .filter(ThirdPartyInsurer.claim_id == claim_id, ThirdPartyInsurer.is_deleted.isnot(True))
            .first()
        )
        if not tpi:
            return None
        cid = tpi.third_party_insurer_id or tpi.third_party_handling_id or tpi.third_party_id
        if cid:
            row = (
                db.query(ClientDetail, Address)
                .outerjoin(Address, Address.id == ClientDetail.address_id)
                .filter(ClientDetail.id == cid)
                .first()
            )
            if row:
                cd, addr = row
                name = " ".join(x for x in [cd.first_name, cd.surname] if x).strip()
                if name:
                    return name
                if addr and (addr.email or "").strip():
                    return addr.email.strip()
        if (tpi.direct_email or "").strip():
            return tpi.direct_email.strip()
        return None

    @staticmethod
    def _other_party(from_email: str, to_list: List[str]) -> Optional[str]:
        """Correspondent = the party that isn't one of our own addresses."""
        ours = {"no-replynationwideassist@outlook.com"}
        mb = (MicrosoftGraphTokenService.mailbox_user("read") or "").strip().lower()
        if mb:
            ours.add(mb)
        ours.add((os.getenv("SENDGRID_SENDER") or "no-replynationwideassist@outlook.com").strip().lower())
        frm = (from_email or "").strip()
        clean_to = [a for a in (to_list or []) if a]
        if frm.lower() in ours:
            for a in clean_to:
                if a.strip().lower() not in ours:
                    return a
            return clean_to[0] if clean_to else (frm or None)
        return frm or (clean_to[0] if clean_to else None)

    @staticmethod
    def import_email(
        db: Session, claim_id: int, filename: str, data: bytes, current_user: Optional[int],
        *, scope_type: str = "claim", scope_id: Optional[int] = None,
    ) -> dict:
        """Parse a dragged-in .eml/.msg, store its attachments in S3, and create an
        Incoming Email (IE) History record against the claim/fleet entity."""
        if scope_id is None:
            scope_id = claim_id
        parsed = parse_email_bytes(filename, data)

        s3 = S3Service()
        att_refs: List[dict] = []
        for att in parsed.get("attachments", []):
            name = att.get("name") or "attachment"
            blob = att.get("data") or b""
            key = f"history/{scope_type}/{scope_id}/emails/{uuid.uuid4().hex}_{name}"
            try:
                s3.client.put_object(
                    Bucket=s3.bucket_name,
                    Key=key,
                    Body=blob,
                    ContentType=att.get("content_type") or "application/octet-stream",
                )
            except Exception as exc:
                print(f"[CaseHistoryService] email attachment upload failed: {exc}")
                continue
            att_refs.append({"name": name, "size": _fmt_size(len(blob)), "s3_key": key})

        from_email = parsed.get("from_email") or ""
        to_list = parsed.get("to") or []
        correspondent = CaseHistoryService._other_party(from_email, to_list)

        handler = None
        if current_user:
            u = db.query(User).filter(User.id == current_user).first()
            if u:
                un = u.user_name or ""
                handler = un.split("@")[0] if "@" in un else (un or None)

        body_text = parsed.get("body_text") or ""
        is_claim = scope_type == "claim"
        tenant_id = (
            db.query(Claim.tenant_id).filter(Claim.id == scope_id).scalar() if is_claim else None
        )
        rec = CaseHistory(
            claim_id=scope_id if is_claim else None,
            scope_type=scope_type,
            scope_id=scope_id,
            tenant_id=tenant_id,
            action_type=CaseHistoryActionType.INCOMING_EMAIL,
            posted_at=parsed.get("date") or datetime.utcnow(),
            correspondent=correspondent,
            handler=handler,
            subject=parsed.get("subject") or None,
            details=(body_text[:500] or None),
            payload={
                "source": "imported_email",
                "from_name": parsed.get("from_name"),
                "from_email": from_email,
                "to": to_list,
                "body_text": body_text,
                "body_html": parsed.get("body_html") or "",
                "attachments": att_refs,
            },
            created_by=current_user,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return _to_dict(rec)

    @staticmethod
    def attachment_bytes(db: Session, record_id: int, index: int):
        """(bytes, filename, content_type) for a stored record's Nth attachment."""
        rec = (
            db.query(CaseHistory)
            .filter(CaseHistory.id == record_id, CaseHistory.is_deleted.isnot(True))
            .first()
        )
        if not rec or not isinstance(rec.payload, dict):
            return None
        atts = rec.payload.get("attachments") or []
        if index < 0 or index >= len(atts):
            return None
        key = (atts[index] or {}).get("s3_key")
        name = (atts[index] or {}).get("name") or "attachment"
        if not key:
            return None
        s3 = S3Service()
        try:
            obj = s3.client.get_object(Bucket=s3.bucket_name, Key=key)
            return (obj["Body"].read(), name, obj.get("ContentType") or "application/octet-stream")
        except Exception as exc:
            print(f"[CaseHistoryService] attachment fetch failed: {exc}")
            return None

    @staticmethod
    def attachment_preview_pages(db: Session, record_id: int, index: int) -> dict:
        """Render a stored attachment as page images (PDF → one PNG per page, via
        PyMuPDF) so the History detail can show the document like the Document
        Library — no browser PDF viewer. Images are returned as data URIs."""
        import base64

        result = CaseHistoryService.attachment_bytes(db, record_id, index)
        if not result:
            return {"type": "unsupported", "pages": []}
        raw, name, content_type = result
        lname = (name or "").lower()
        ctype = (content_type or "").lower()

        if ctype.startswith("image/") or lname.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            b64 = base64.b64encode(raw).decode("utf-8")
            mime = ctype if ctype.startswith("image/") else "image/png"
            return {"type": "image", "file_name": name, "url": f"data:{mime};base64,{b64}", "pages": []}

        if "pdf" in ctype or lname.endswith(".pdf"):
            try:
                import fitz
                pdf = fitz.open(stream=raw, filetype="pdf")
                pages = []
                for i in range(len(pdf)):
                    pix = pdf.load_page(i).get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
                    b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                    pages.append({"page": i + 1, "image": f"data:image/png;base64,{b64}"})
                pdf.close()
                return {"type": "pdf", "file_name": name, "pages": pages}
            except Exception as exc:
                print(f"[CaseHistoryService] PDF preview render failed: {exc}")
                return {"type": "unsupported", "file_name": name, "pages": []}

        return {"type": "unsupported", "file_name": name, "pages": []}

    @staticmethod
    def claim_emails(db: Session, claim_id: int) -> List[dict]:
        """Emails matching this claim's case reference, shaped as read-only History
        records. See ``emails_by_reference``."""
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            return []
        return CaseHistoryService.emails_by_reference(
            db, build_case_reference(claim.id, db), scope_type="claim", scope_id=claim_id,
        )

    @staticmethod
    def emails_by_reference(db: Session, reference: str, *, scope_type: str, scope_id: int) -> List[dict]:
        """Emails (sent + received) whose subject/body mention ``reference``, pulled
        live from the configured Outlook mailbox via Microsoft Graph, shaped as
        read-only History records (SE for outgoing, IE for incoming). Claims and
        Fleet share one mailbox but pass their own reference. Best-effort."""
        if not reference:
            return []
        try:
            token = MicrosoftGraphTokenService.get_access_token("read")
            if not token:
                return []
            items = OutlookCaseActivityService.get_case_emails(
                claim_reference=reference, access_token=token
            )
        except Exception as exc:  # never let a mailbox hiccup break the History screen
            print(f"[CaseHistoryService] email fetch error: {exc}")
            return []

        # Our own addresses (read mailbox + the noreply we send from) — the
        # correspondent is the OTHER party, never one of these.
        import os
        ours = {"no-replynationwideassist@outlook.com"}
        mb = (MicrosoftGraphTokenService.mailbox_user("read") or "").strip().lower()
        if mb:
            ours.add(mb)
        ours.add((os.getenv("SENDGRID_SENDER") or "no-replynationwideassist@outlook.com").strip().lower())

        def _correspondent(item) -> Optional[str]:
            frm = (item.sender_email or "").strip()
            to_list = [a for a in ((item.meta or {}).get("to_recipients") or []) if a]
            if frm.lower() in ours:
                # Sent by us (e.g. from the noreply) → correspondent = the recipient.
                for a in to_list:
                    if a.strip().lower() not in ours:
                        return a
                return to_list[0] if to_list else (frm or None)
            # Received → the sender is the correspondent.
            return frm or (to_list[0] if to_list else None)

        out: List[dict] = []
        for i, it in enumerate(items):
            attachments = [
                {"name": a.file_name, "url": a.file_url, "size": a.file_size}
                for a in (it.attachments or [])
            ]
            # Sent from one of our mailboxes → Send Email (SE); otherwise it landed
            # in the inbox from the other party → Incoming Email (IE).
            outgoing = (it.sender_email or "").strip().lower() in ours
            out.append({
                "id": f"email:{i}",
                "claim_id": scope_id if scope_type == "claim" else None,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "action_type": "send_email" if outgoing else "incoming_email",
                "posted_at": it.received_at,
                "correspondent": _correspondent(it),
                "handler": it.sender_name or None,
                "subject": it.subject or None,
                "details": it.body_preview or None,
                "payload": {
                    "source": "email",
                    # Graph message id — lets the History detail pane reply/forward
                    # this email through the same Case Activity email endpoints.
                    "message_id": (it.meta or {}).get("message_id") or it.id or None,
                    "from_name": it.sender_name,
                    "from_email": it.sender_email,
                    "to": (it.meta or {}).get("to_recipients") or [],
                    "body_html": it.body_html,
                    "body_text": it.body_text,
                    "attachments": attachments,
                },
                "created_by": None,
                "created_at": it.received_at,
            })
        return out

    # Reference prefixes staff put in the subject/body so the shared mailbox can be
    # filtered per fleet entity (claims use the case reference).
    _SCOPE_PREFIX = {"fleet_hire": "FH", "vm_cams": "CAMS", "vm_skyline": "SKY"}

    @staticmethod
    def scope_reference(db: Session, scope_type: str, scope_id: int) -> str:
        if scope_type == "claim":
            return build_case_reference(scope_id, db)
        prefix = CaseHistoryService._SCOPE_PREFIX.get(scope_type, scope_type.upper())
        return f"{prefix}-{scope_id}"

    @staticmethod
    def scope_emails(db: Session, scope_type: str, scope_id: int) -> List[dict]:
        if scope_type == "claim":
            return CaseHistoryService.claim_emails(db, scope_id)
        return CaseHistoryService.emails_by_reference(
            db, CaseHistoryService.scope_reference(db, scope_type, scope_id),
            scope_type=scope_type, scope_id=scope_id,
        )

    @staticmethod
    def filter_options(db: Session, claim_id: int) -> dict:
        return CaseHistoryService.filter_options_for_scope(db, "claim", claim_id)

    @staticmethod
    def filter_options_for_scope(db: Session, scope_type: str, scope_id: int) -> dict:
        rows = (
            db.query(CaseHistory)
            .filter(_scope_clause(scope_type, scope_id), CaseHistory.is_deleted.isnot(True))
            .all()
        )
        return {
            "correspondents": sorted({r.correspondent for r in rows if r.correspondent}),
            "handlers": sorted({r.handler for r in rows if r.handler}),
            "action_types": sorted({r.action_type.value for r in rows if r.action_type}),
        }
