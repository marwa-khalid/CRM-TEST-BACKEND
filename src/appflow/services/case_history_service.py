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

from libdata.enums import CaseHistoryActionType, PersonRoleEnum
from libdata.models.tables import (
    CaseHistory,
    Claim,
    ThirdPartyInsurer,
    ClientDetail,
    Address,
    User,
    HireVehicleProvided,
)
from appflow.services.microsoft_graph_token_service import MicrosoftGraphTokenService
from appflow.services.outlook_case_activity_service import OutlookCaseActivityService
from appflow.services.s3_service import S3Service
from appflow.services.case_email_import import parse_email_bytes
from appflow.utils import build_case_reference, handler_name_for_user


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
        # (the claim's third-party email) when the caller didn't supply them.
        if is_claim:
            if handler is None and claim_row is not None:
                h = getattr(claim_row, "handler", None)
                handler = (getattr(h, "label", "") or "") or None
            if correspondent is None:
                correspondent = CaseHistoryService._claim_tpi_correspondent(db, scope_id)
        # Fall back to the user who performed the action when there's no handler on the
        # claim (or for fleet records) — otherwise the row shows a bare "-".
        if handler is None and current_user:
            handler = handler_name_for_user(db, current_user) or None

        att_refs: List[dict] = []
        docs = [d for d in (documents or []) if d.get("data")]
        if docs:
            s3 = S3Service()
            for doc in docs:
                name = doc.get("name") or "document"
                blob = doc.get("data") or b""
                # NB: the S3 IAM policy only grants access under the "claims/" prefix.
                key = f"claims/history/{scope_type}/{scope_id}/docs/{uuid.uuid4().hex}_{name}"
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

        # Correspondent = the "Email Address" from each case's Third Party Details
        # (ThirdPartyInsurer.third_party_id → Address.email) — one per case. The
        # insurer / handling-agent / direct-email addresses are deliberately excluded.
        client_ids = {tpi.third_party_id for tpi in tpis if tpi.third_party_id}

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

        # Only correspondents with an email, de-duplicated by email, alphabetical.
        seen, result = set(), []
        for c in sorted(out, key=lambda x: (x["email"] or "").lower()):
            e = c.get("email")
            if e and e.lower() not in seen:
                seen.add(e.lower())
                result.append(c)
        return result

    @staticmethod
    def _cams_vehicle_claim_id(db: Session, vehicle_record_id: int) -> Optional[int]:
        """The claim a CAMS vehicle is on hire against — matched by registration
        number to the claims-side hire vehicle (there's no FK link on the fleet side)."""
        from fleet.models.tables import FleetVehicleRecord
        rec = db.query(FleetVehicleRecord).filter(FleetVehicleRecord.id == vehicle_record_id).first()
        reg = (getattr(rec, "registration_number", "") or "").replace(" ", "").upper()
        if not reg:
            return None
        rows = (
            db.query(HireVehicleProvided.claim_id, HireVehicleProvided.hire_vehicle_registration)
            .filter(HireVehicleProvided.hire_vehicle_registration.isnot(None))
            .all()
        )
        for claim_id, hv_reg in rows:
            if (hv_reg or "").replace(" ", "").upper() == reg:
                return claim_id
        return None

    @staticmethod
    def _claim_client_email(db: Session, claim_id: int) -> Optional[str]:
        """The claim's client (driver) email from Client Details."""
        row = (
            db.query(ClientDetail, Address)
            .outerjoin(Address, Address.id == ClientDetail.address_id)
            .filter(ClientDetail.claim_id == claim_id, ClientDetail.role == PersonRoleEnum.CLIENT)
            .first()
        )
        if row:
            _cd, addr = row
            if addr and (addr.email or "").strip():
                return addr.email.strip()
        return None

    @staticmethod
    def scope_correspondents(db: Session, scope_type: str, scope_id: int) -> dict:
        """Correspondent options for the History correspondent field, per scope.
        Returns {"default": <email|null>, "options": [emails]}.
        - claim: tenant-wide Third Party emails.
        - vm_cams: the linked claim's Client email (default) + Third Party emails.
        - vm_skyline / fleet_hire: driver email is supplied by the frontend, so [].
        """
        emails: List[str] = []
        default = None
        if scope_type == "claim":
            emails = [c["email"] for c in CaseHistoryService.correspondents(db, scope_id) if c.get("email")]
        elif scope_type == "vm_cams":
            claim_id = CaseHistoryService._cams_vehicle_claim_id(db, scope_id)
            if claim_id:
                default = CaseHistoryService._claim_client_email(db, claim_id)
                tps = [c["email"] for c in CaseHistoryService.correspondents(db, claim_id) if c.get("email")]
                emails = ([default] if default else []) + tps
        # De-dup, preserve order (default/client first).
        seen, options = set(), []
        for e in emails:
            k = (e or "").lower()
            if e and k not in seen:
                seen.add(k)
                options.append(e)
        return {"default": default, "options": options}

    @staticmethod
    def _claim_tpi_correspondent(db: Session, claim_id: int) -> Optional[str]:
        """The correspondent auto-filled on payment-pack / letter records: the
        "Email Address" from the claim's Third Party Details
        (ThirdPartyInsurer.third_party_id → Address.email)."""
        tpi = (
            db.query(ThirdPartyInsurer)
            .filter(ThirdPartyInsurer.claim_id == claim_id, ThirdPartyInsurer.is_deleted.isnot(True))
            .first()
        )
        if not tpi or not tpi.third_party_id:
            return None
        row = (
            db.query(ClientDetail, Address)
            .outerjoin(Address, Address.id == ClientDetail.address_id)
            .filter(ClientDetail.id == tpi.third_party_id)
            .first()
        )
        if row:
            _cd, addr = row
            if addr and (addr.email or "").strip():
                return addr.email.strip()
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
            # NB: the S3 IAM policy only grants access under the "claims/" prefix.
            key = f"claims/history/{scope_type}/{scope_id}/emails/{uuid.uuid4().hex}_{name}"
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
            pages = CaseHistoryService._pdf_bytes_to_pages(raw)
            if pages is None:
                return {"type": "unsupported", "file_name": name, "pages": []}
            return {"type": "pdf", "file_name": name, "pages": pages}

        # Office documents (Word / Excel / PowerPoint). Preferred path: convert to PDF
        # with headless LibreOffice and render exact page-image snapshots — pixel-for-
        # pixel the real document, same quality as the PDF preview. When LibreOffice
        # isn't installed we fall back to a best-effort HTML rendering.
        is_word = "wordprocessingml" in ctype or lname.endswith(".docx")
        is_excel = "spreadsheetml" in ctype or lname.endswith((".xlsx", ".xls"))
        is_ppt = "presentationml" in ctype or lname.endswith((".pptx", ".ppt"))
        is_legacy_doc = "msword" in ctype or lname.endswith(".doc")

        # The payment-pack "Word" download is actually an HTML document with a .doc
        # extension — render its HTML as-is (already a designed template).
        if is_legacy_doc:
            text = raw.decode("utf-8", "ignore")
            if "<html" in text.lower() or "<body" in text.lower():
                return {"type": "html", "file_name": name, "html": text, "pages": []}

        if is_word or is_excel or is_ppt or is_legacy_doc:
            suffix = "." + (lname.rsplit(".", 1)[-1] if "." in lname else
                            ("docx" if is_word else "xlsx" if is_excel else "pptx"))
            pdf_bytes = CaseHistoryService._office_to_pdf(raw, suffix)
            if pdf_bytes:
                pages = CaseHistoryService._pdf_bytes_to_pages(pdf_bytes, crop=not is_excel)
                if pages:
                    return {"type": "pdf", "file_name": name, "pages": pages}
            # LibreOffice unavailable / failed → HTML fallback.
            try:
                if is_word:
                    return {"type": "html", "file_name": name, "html": CaseHistoryService._docx_to_html(raw), "pages": []}
                if is_excel and lname.endswith(".xlsx"):
                    return {"type": "html", "file_name": name, "html": CaseHistoryService._xlsx_to_html(raw), "pages": []}
            except Exception as exc:
                print(f"[CaseHistoryService] Office HTML fallback failed: {exc}")
            return {"type": "unsupported", "file_name": name, "pages": []}

        return {"type": "unsupported", "file_name": name, "pages": []}

    @staticmethod
    def _soffice_bin() -> Optional[str]:
        """Locate the headless LibreOffice binary, if installed."""
        import os
        import shutil
        for cand in ("soffice", "libreoffice"):
            found = shutil.which(cand)
            if found:
                return found
        for path in (
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",  # macOS cask
            "/usr/bin/soffice",
            "/usr/lib/libreoffice/program/soffice",  # nixpacks / debian
        ):
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _office_to_pdf(raw: bytes, suffix: str) -> Optional[bytes]:
        """Convert an Office document (docx/xlsx/pptx/…) to PDF bytes via headless
        LibreOffice so it can be rendered as exact page-image snapshots. Returns None
        when LibreOffice isn't installed or the conversion fails (caller falls back)."""
        soffice = CaseHistoryService._soffice_bin()
        if not soffice:
            return None
        import glob
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, f"in{suffix}")
            with open(src, "wb") as fh:
                fh.write(raw)
            profile = os.path.join(tmp, "profile")  # isolated per-call user profile
            try:
                subprocess.run(
                    [soffice, "--headless", "--norestore", "--nolockcheck", "--nodefault",
                     f"-env:UserInstallation=file://{profile}",
                     "--convert-to", "pdf", "--outdir", tmp, src],
                    check=True, capture_output=True, timeout=120,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[CaseHistoryService] LibreOffice convert failed: {exc}")
                return None
            pdfs = glob.glob(os.path.join(tmp, "*.pdf"))
            if not pdfs:
                return None
            with open(pdfs[0], "rb") as fh:
                return fh.read()

    @staticmethod
    def _pdf_bytes_to_pages(raw: bytes, crop: bool = True) -> Optional[list]:
        """Render PDF bytes to a list of {page, image(data-uri PNG)} via PyMuPDF.
        ``crop`` trims surrounding white margins and skips fully-blank pages (good for
        letters/documents); pass crop=False for spreadsheets where the sheet grid /
        page extent should be preserved. Returns None on a render error."""
        import base64
        import io
        try:
            import fitz
            from PIL import Image, ImageChops
        except Exception as exc:  # noqa: BLE001
            print(f"[CaseHistoryService] PDF render deps missing: {exc}")
            return None
        try:
            pdf = fitz.open(stream=raw, filetype="pdf")
            pages = []
            page_no = 0
            for i in range(len(pdf)):
                pix = pdf.load_page(i).get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                if crop:
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bbox = ImageChops.difference(img, bg).getbbox()
                    if not bbox:
                        continue  # entirely blank page — skip
                    pad = 12
                    l, t, r2, b2 = bbox
                    img = img.crop((max(0, l - pad), max(0, t - pad),
                                    min(img.width, r2 + pad), min(img.height, b2 + pad)))
                out = io.BytesIO()
                img.save(out, "PNG")
                page_no += 1
                b64 = base64.b64encode(out.getvalue()).decode("utf-8")
                pages.append({"page": page_no, "image": f"data:image/png;base64,{b64}"})
            pdf.close()
            return pages
        except Exception as exc:  # noqa: BLE001
            print(f"[CaseHistoryService] PDF preview render failed: {exc}")
            return None

    @staticmethod
    def _docx_to_html(data: bytes) -> str:
        """Render a .docx as HTML, preserving run formatting (bold/italic/underline),
        paragraph alignment and tables in document order. Not a pixel-perfect Word
        render (that needs LibreOffice) but keeps the document's structure + emphasis."""
        import io
        import html as _html
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(io.BytesIO(data))
        align = {1: "center", 2: "right", 3: "justify"}  # WD_ALIGN_PARAGRAPH values

        def render_para(p) -> str:
            runs = []
            for run in p.runs:
                t = _html.escape(run.text)
                if not t:
                    continue
                if run.bold:
                    t = f"<strong>{t}</strong>"
                if run.italic:
                    t = f"<em>{t}</em>"
                if run.underline:
                    t = f"<u>{t}</u>"
                runs.append(t)
            inner = "".join(runs)
            if not inner.strip():
                return ""  # skip empty paragraphs — they only add white space
            a = align.get(getattr(p, "alignment", None), "left")
            return f"<p style='margin:3px 0;text-align:{a}'>{inner}</p>"

        parts: List[str] = []
        for child in doc.element.body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                html_p = render_para(Paragraph(child, doc))
                if html_p:
                    parts.append(html_p)
            elif tag == "tbl":
                rows = []
                for row in Table(child, doc).rows:
                    cells = "".join(
                        "<td style='border:1px solid #d1d5db;padding:4px 8px;vertical-align:top'>"
                        + (("".join(filter(None, [render_para(cp) for cp in cell.paragraphs]))) or "&nbsp;")
                        + "</td>"
                        for cell in row.cells
                    )
                    rows.append(f"<tr>{cells}</tr>")
                parts.append(f"<table style='border-collapse:collapse;margin:10px 0;width:100%'>{''.join(rows)}</table>")
        return (
            "<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111827;line-height:1.5\">"
            + "".join(parts) + "</div>"
        )

    @staticmethod
    def _xlsx_to_html(data: bytes) -> str:
        """Render a .xlsx workbook as HTML tables (one per sheet) via openpyxl."""
        import io
        import html as _html
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        parts: List[str] = []
        for ws in wb.worksheets:
            rows_html = []
            for row in ws.iter_rows(values_only=True):
                if all(c is None for c in row):
                    continue  # skip blank rows
                cells = "".join(
                    "<td style='border:1px solid #d1d5db;padding:3px 7px;white-space:nowrap'>"
                    + _html.escape("" if c is None else str(c))
                    + "</td>"
                    for c in row
                )
                rows_html.append(f"<tr>{cells}</tr>")
            if not rows_html:
                continue
            parts.append(f"<div style='font-weight:600;margin:12px 0 4px'>{_html.escape(ws.title)}</div>")
            parts.append(f"<table style='border-collapse:collapse;margin:0 0 12px'>{''.join(rows_html)}</table>")
        wb.close()
        return (
            "<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#111827\">"
            + ("".join(parts) or "<p>Empty workbook.</p>") + "</div>"
        )

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
