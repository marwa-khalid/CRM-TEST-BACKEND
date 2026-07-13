# app/services/claims_service.py
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from fastapi import HTTPException,BackgroundTasks, status,Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from libdata.models.tables import (Claim, SourceChannel, User, Address,ClientDetail,LocationCondition,
                                   HireVehicleProvided,Referrer,DriverCommission,ReferrerCommission,
                                   VehicleDetail,Borough,ThirdPartyVehicle,PoliceDetail,EngineerDetail,
                                    RouteRepair,TotalLoss,InsurerBroker,PanelSolicitor,Storage,Recovery,
                                   ThirdPartyInsurer,HireDetail,DriverDocumentAgreement,DriverCheck,
                                   DriverCheckImage,VehicleStatus,Handler,ABIBHRCharges)
from appflow.utils import get_tenant_id, handler_name_for_claim
from appflow.models.claims import ClaimListOut,ClaimDisplayLabels
from libdata.enums import PersonRoleEnum,HistoryLogType
from appflow.services.history_activity_service import HistoryActivityService
from appflow.services.graph_email_service import GraphEmailService
from appflow.logger import logger
import base64
import csv
import io
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, To, ReplyTo, Attachment, FileContent, FileName, FileType, Disposition, ContentId,
)

_BASE_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
try:
    with open(os.path.join(_BASE_TEMPLATE_DIR, "logo.png"), "rb") as _lf:
        LOGO_ENCODED = base64.b64encode(_lf.read()).decode()
except Exception:
    LOGO_ENCODED = ""

def _labels_bundle(c: Claim) -> Dict[str, Any]:
    return {
        "claim_type": c.claim_type.label if c.claim_type else None,
        # Handler = the user who owns/created the claim (their username).
        "handler": handler_name_for_claim(c) or (c.handler.label if c.handler else None),
        "target_debt": c.target_debt.label if c.target_debt else None,
        "case_status": c.case_status.label if c.case_status else None,
        "source": c.source.label if c.source else None,
        "source_staff_user": (f"{c.source_staff_user.first_name or ''} {c.source_staff_user.last_name or ''}".strip()
                              if getattr(c, "source_staff_user", None) else None),
        "prospect": c.prospect.label if c.prospect else None,
        "present_position": c.present_position.label if c.present_position else None,
    }


def _require_staff_if_needed(db: Session, source_id: Optional[int], staff_user_id: Optional[int]):
    if not source_id:
        return
    src = db.get(SourceChannel, source_id)
    if not src or not src.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or inactive source.")
    if src.requires_staff:
        if not staff_user_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Staff member is required for Staff Marketing.")
        handler = db.get(Handler, staff_user_id)
        if not handler or not handler.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected staff user is invalid or inactive.")


def _validate_abroad(payload: Dict[str, Any]):
    if payload.get("client_going_abroad") and not payload.get("abroad_date"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "abroad_date is required when client_going_abroad is true.")


def _send_email(recipients: list, subject: str, html_content: str):
    """Best-effort notification email. Never raises — email failures must not
    break the calling request (it runs as a background task anyway).

    Prefers Microsoft Graph (delivered from a real Outlook mailbox); falls back
    to SendGrid only if Graph is unavailable or fails.
    """
    recipient_list = [r for r in recipients if r and "@" in r]
    if not recipient_list:
        logger.warning("notify email skipped: no valid recipients")
        return

    # Prefer Graph — a real Outlook mailbox actually gets delivered, and it
    # auto-attaches the logo inline when the HTML uses cid:companylogo.
    if GraphEmailService.is_configured():
        result = GraphEmailService.send_mail(recipient_list, subject, html_content)
        if result is not None:
            return
        logger.warning("Graph send failed for notify email; falling back to SendGrid")

    key = os.getenv("SENDGRID_API_KEY")
    if not key:
        logger.warning("notify email skipped: SENDGRID_API_KEY not configured")
        return
    message = Mail(
        from_email="No-Reply <no-replynationwideassist@outlook.com>",  # Format: "Name <email>"
        to_emails=[To(email) for email in recipient_list],
        subject=subject,
        html_content=html_content,
    )
    # Explicitly tell mail clients where replies should NOT go
    message.reply_to = ReplyTo("no-replynationwideassist@outlook.com", "No-Reply")
    # Inline logo so cid:companylogo renders on the SendGrid fallback path too.
    if LOGO_ENCODED and "cid:companylogo" in (html_content or ""):
        message.add_attachment(Attachment(
            FileContent(LOGO_ENCODED), FileName("logo.png"),
            FileType("image/png"), Disposition("inline"), ContentId("companylogo"),
        ))
    try:
        SendGridAPIClient(key).send(message)
        logger.info(f"notify email sent to {recipient_list}")
    except Exception as e:
        # e.g. DNS/network failure reaching api.sendgrid.com, or SendGrid rejection.
        logger.warning(f"notify email to {recipient_list} failed: {e}")

# ---------- CRUD ----------

def create_claim(db: Session, payload: Dict[str, Any], current_user_id: int, tenant_id: int) -> Claim:
    _validate_abroad(payload)
    _require_staff_if_needed(db, payload.get("source_id"), payload.get("source_staff_user_id"))

    claim = Claim(**payload)
    claim.entrant_user_id = current_user_id  # who opened the file (username shown in UI via User)
    claim.tenant_id = tenant_id
    # claim.created_by = current_user_id
    # claim.updated_by = current_user_id
    db.add(claim)
    db.commit()  # assign PK
    db.refresh(claim)
    # claim.labels = _labels_bundle(claim)  # type: ignore[attr-defined]
    current_yyyymm = datetime.now().strftime("%Y%m")
    padded_claim_id = str(claim.id).zfill(5)
    HistoryActivityService.create_activity(
        db=db,
        claim_id=claim.id,
        file_name=f"The general detail has been created for claim-{current_yyyymm}-{padded_claim_id}",
        file_path="",
        file_type=HistoryLogType.CREATED_GENERAL_DETAIL,
        user_id=current_user_id,
        tenant_id=tenant_id
    )

    # (#8) New claim created -> notify the creator. (#11) Client abroad -> alert.
    try:
        from appflow.services.notification_service import safe_notify
        from appflow.utils import build_case_reference
        ref = build_case_reference(claim.id, db)
        safe_notify(
            db, recipient_user_id=current_user_id, tenant_id=tenant_id, actor_user_id=current_user_id,
            category="Claim", tab="Claims", title="New Claim Created",
            description=f"Claim {ref} was created.", claim_id=claim.id,
        )
        if payload.get("client_going_abroad"):
            safe_notify(
                db, recipient_user_id=current_user_id, tenant_id=tenant_id, actor_user_id=current_user_id,
                category="Claim", tab="Claims", title="Client Going Abroad",
                description=f"Client on {ref} is going abroad — manager attention required.", claim_id=claim.id,
                email=True,
            )
    except Exception:
        db.rollback()
    return claim


def get_claim(claim_id: int, tenant_id: int, db: Session) -> Claim:
    claim = db.query(Claim).filter(Claim.id == claim_id, Claim.tenant_id == tenant_id).first()
    return claim


from sqlalchemy import text


def list_claims(tenant_id: int,
                db: Session,
                page: int = 1,
                page_size: int = 20,
                handler_id: Optional[int] = None,
                case_status_id: Optional[int] = None,
                search: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
    # Base query with joins to get actual labels for each foreign key
    sql = """
        SELECT 
            c.id,
            c.claim_type_id, ct.label AS claim_type_label,
            c.handler_id, COALESCE(NULLIF(SPLIT_PART(cu.user_name, '@', 1), ''), h.label) AS handler_label,
            c.target_debt_id, td.label AS target_debt_label,
            c.case_status_id, cs.label AS case_status_label,
            c.source_id, s.label AS source_label,
            c.source_staff_user_id, ss.first_name || ' ' || ss.last_name AS source_staff_label,  -- Staff user name
            c.prospects_id, p.label AS prospect_label,
            c.present_position_id, pfp.label AS present_position_label,
            c.credit_hire_accepted, c.non_fault_accident, c.any_passengers,
            c.client_injured, c.file_opened_at, c.file_closed_at, c.file_closed_reason, c.is_locked,
            c.client_going_abroad, c.abroad_date, c.manager_notified_at, c.rejection_reason
        FROM claims c
        LEFT JOIN claim_types ct ON c.claim_type_id = ct.id
        LEFT JOIN handlers h ON c.handler_id = h.id
        LEFT JOIN users cu ON c.created_by = cu.id  -- Handler = the claim's owner/creator
        LEFT JOIN target_debts td ON c.target_debt_id = td.id
        LEFT JOIN case_statuses cs ON c.case_status_id = cs.id
        LEFT JOIN source_channels s ON c.source_id = s.id
        LEFT JOIN users ss ON c.source_staff_user_id = ss.id  -- Getting the full name (first_name and last_name) of staff
        LEFT JOIN prospects p ON c.prospects_id = p.id
        LEFT JOIN present_file_positions pfp ON c.present_position_id = pfp.id
        WHERE c.is_active = true and c.tenant_id = :tenant_id
    """

    # Filtering
    if handler_id:
        sql += f" AND c.handler_id = :handler_id"
    if case_status_id:
        sql += f" AND c.case_status_id = :case_status_id"
    if search:
        if search.isdigit():
            sql += f" AND c.id = :search"
        else:
            sql += f" AND COALESCE(c.file_closed_reason, '') ILIKE :search"

    # Pagination
    sql += " ORDER BY c.id DESC LIMIT :limit OFFSET :offset"

    # Get the total count
    total_sql = """
        SELECT COUNT(*) FROM claims c
        LEFT JOIN claim_types ct ON c.claim_type_id = ct.id
        LEFT JOIN handlers h ON c.handler_id = h.id
        LEFT JOIN target_debts td ON c.target_debt_id = td.id
        LEFT JOIN case_statuses cs ON c.case_status_id = cs.id
        LEFT JOIN source_channels s ON c.source_id = s.id
        LEFT JOIN users ss ON c.source_staff_user_id = ss.id
        LEFT JOIN prospects p ON c.prospects_id = p.id
        LEFT JOIN present_file_positions pfp ON c.present_position_id = pfp.id
        WHERE c.is_active = true
    """
    if handler_id:
        total_sql += f" AND c.handler_id = :handler_id"
    if case_status_id:
        total_sql += f" AND c.case_status_id = :case_status_id"
    if search:
        if search.isdigit():
            total_sql += f" AND c.id = :search"
        else:
            total_sql += f" AND COALESCE(c.file_closed_reason, '') ILIKE :search"

    # Execute queries
    result = db.execute(text(sql), {
        "tenant_id": tenant_id,
        "handler_id": handler_id,
        "case_status_id": case_status_id,
        "search": f"%{search}%" if search and not search.isdigit() else None,
        "limit": page_size,
        "offset": (page - 1) * page_size,
        "search": search
    }).fetchall()

    # Total count
    total = db.execute(text(total_sql), {
        "handler_id": handler_id,
        "case_status_id": case_status_id,
        "search": f"%{search}%" if search and not search.isdigit() else None,
    }).scalar()

    # Process rows
    rows = [dict(r) for r in result]

    return rows, total


def update_claim(db: Session, claim_id: int,user_id: int,tenant_id: int, payload: Dict[str, Any]) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found.")
    # if claim.is_locked:
    #     raise HTTPException(status.HTTP_409_CONFLICT, "Claim is closed/locked.")

    # validations
    merged = {**{k: getattr(claim, k) for k in [
        "source_id", "source_staff_user_id", "client_going_abroad", "abroad_date"
    ]}, **payload}
    _validate_abroad(merged)
    _require_staff_if_needed(db, merged.get("source_id"), merged.get("source_staff_user_id"))

    changed_fields = []
    status_changed = False
    abroad_changed = False
    for k, v in payload.items():
        old = getattr(claim, k)
        if old != v:
            pretty_label = ClaimDisplayLabels.format(k)
            changed_fields.append(pretty_label)
            if k == "case_status_id":
                status_changed = True
            if k == "client_going_abroad" and v:
                abroad_changed = True
            setattr(claim, k, v)

    claim.updated_by = user_id
    db.commit()
    db.refresh(claim)
    if changed_fields:
        file_path = ", ".join(changed_fields)
        current_yyyymm = datetime.now().strftime("%Y%m")
        padded_claim_id = str(claim.id).zfill(5)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=claim.id,
            file_name=f"The general detail updated for claim-{current_yyyymm}-{padded_claim_id}",
            file_path=file_path,
            file_type=HistoryLogType.UPDATED_GENERAL_DETAIL,
            user_id=user_id,
            tenant_id=tenant_id
        )

    # Notify the actor when the case status changes.
    if status_changed:
        try:
            from appflow.services.notification_service import create_notification
            from appflow.utils import build_case_reference
            from libdata.models.tables import CaseStatus
            label = ""
            if claim.case_status_id:
                cs = db.query(CaseStatus).filter(CaseStatus.id == claim.case_status_id).first()
                label = (cs.label if cs else "") or ""
            ref = build_case_reference(claim.id, db)
            create_notification(
                db,
                recipient_user_id=user_id,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                category="Claim",
                tab="Claims",
                title="Claim Status Updated",
                description=(f"{ref} status changed to {label}." if label else f"{ref} status updated."),
                claim_id=claim.id,
            )
        except Exception:
            db.rollback()

    # (#11) Client going abroad -> alert (manager attention).
    if abroad_changed:
        try:
            from appflow.services.notification_service import safe_notify
            from appflow.utils import build_case_reference
            ref = build_case_reference(claim.id, db)
            safe_notify(
                db, recipient_user_id=user_id, tenant_id=tenant_id, actor_user_id=user_id,
                category="Claim", tab="Claims", title="Client Going Abroad",
                description=f"Client on {ref} is going abroad — manager attention required.", claim_id=claim.id,
                email=True,
            )
        except Exception:
            db.rollback()
    # claim.labels = _labels_bundle(claim)  # type: ignore[attr-defined]
    return claim


def close_claim(db: Session, claim_id: int, reason: str, user_id: int = None, tenant_id: int = None) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found.")
    if claim.is_locked:
        return claim
    if not reason or not reason.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Closure reason is required.")

    claim.file_closed_reason = reason.strip()
    claim.file_closed_at = datetime.now(timezone.utc)
    claim.is_locked = True

    db.commit()
    db.refresh(claim)

    # Notify the actor that the claim was closed.
    if user_id:
        try:
            from appflow.services.notification_service import create_notification
            from appflow.utils import build_case_reference
            ref = build_case_reference(claim.id, db)
            create_notification(
                db,
                recipient_user_id=user_id,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                category="Claim",
                tab="Claims",
                title="Claim Closed",
                description=f"{ref} was closed.",
                claim_id=claim.id,
                email=True,
            )
        except Exception:
            db.rollback()
    # claim.labels = _labels_bundle(claim)  # type: ignore[attr-defined]
    return claim


def notify_manager(db: Session, claim_id: int,recipient:str, background_tasks: BackgroundTasks) -> Claim:
    
    claim = db.get(Claim, claim_id)
    
    # ... (Your existing validation logic) ...

    # Pull list from your system settings
    recipients = [recipient]
    formatted_now = datetime.now().strftime("%d-%m-%y")
    subject = "Notification of Vulnerable Person"
    year_month = datetime.now().strftime("%Y%m")
    case_id = None
    if claim:
        case_id = f"{year_month}-{claim.id:04d}"
    
    # 1. Start with an empty string
    case_row = ""

    # 2. Add Case ID row if it exists
    if case_id:
        case_row += f"""
            <tr>
                <td width="136" style="color: #444444; font-size: 12px; font-weight: 400;">Case No</td>
                <td style="color: #444444; font-size: 12px; font-weight: 600;">{case_id}</td>
            </tr>
            <tr><td colspan="2" style="height: 8px;"></td></tr>
            <tr><td colspan="2" style="height: 1px; background-color: #CCCCCC;"></td></tr>
            <tr><td colspan="2" style="height: 8px;"></td></tr>
        """

    # 3. Add Client Name row if it exists
    client_record = db.query(ClientDetail).filter(ClientDetail.claim_id == claim_id).first()

    # 2. Build the display name
    client_display_name = "N/A"
    if client_record:
        # Combine first name and surname
        first_name = getattr(client_record, 'first_name', '')
        surname = getattr(client_record, 'surname', '')
        client_display_name = f"{first_name} {surname}".strip()
    elif hasattr(claim, 'client_name') and claim.client_name:
        # Fallback to the original field if record doesn't exist
        client_display_name = claim.client_name

    # 3. Add to your case_row
    if client_display_name != "N/A":
        case_row += f"""
            <tr>
                <td width="136" style="color: #444444; font-size: 12px; font-weight: 400;">Client Name:</td>
                <td style="color: #444444; font-size: 12px; font-weight: 600;">{client_display_name}</td>
            </tr>
            <tr><td colspan="2" style="height: 8px;"></td></tr>
            <tr><td colspan="2" style="height: 1px; background-color: #CCCCCC;"></td></tr>
            <tr><td colspan="2" style="height: 8px;"></td></tr>
        """
    # The Template from your image (logo travels inline as cid:companylogo)
    logo_url = "cid:companylogo"

    html_body = f"""
    <html>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: Arial, sans-serif;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff;">
            <tr>
                <td align="center" style="padding: 40px 20px;">
                    
                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                        <tr>
                            <td align="center">
                                <img src="{logo_url}" alt="Nationwide Assist" width="48" style="display: block; border: 0; outline: none; text-decoration: none; height: auto; margin: 0 auto;">
                            </td>
                        </tr>
                    </table>

                    <table width="100%" border="0" cellspacing="0" cellpadding="16" style="max-width: 380px; border: 1px solid #CCCCCC; border-radius: 8px; background-color: #ffffff;">
                        <tr>
                            <td>
                                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                    {case_row}
                                    <tr>
                                        <td width="136" style="color: #444444; font-size: 12px; font-weight: 400;">Date</td>
                                        <td style="color: #444444; font-size: 12px; font-weight: 600;">{formatted_now}</td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>

                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 345px; margin-top: 24px;">
                        <tr>
                            <td align="center" style="color: #444444; font-size: 14px; font-weight: 400; line-height: 1.5;">
                                Please note the above client has been identified as a vulnerable person.<br/>
                                Kindly review the case and advise if any additional actions or support are required.
                            </td>
                        </tr>
                    </table>

                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; margin-top: 40px; margin-bottom: 24px;">
                        <tr><td style="height: 1px; background-color: #CCCCCC;"></td></tr>
                    </table>

                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                        <tr>
                            <td align="center" style="color: #444444;">
                                <span style="font-size: 12px; font-weight: 600;">Kind regards,</span><br/>
                                <span style="font-size: 14px; font-weight: 600; display: inline-block; margin-top: 4px;">Nationwide Assist IT / Systems Team</span>
                            </td>
                        </tr>
                    </table>

                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    # Trigger via SendGrid in the background
    background_tasks.add_task(_send_email, recipients, subject, html_body)
    if not claim:
        return {"detail": "Manager Notified"}
    # Database updates
    if claim:
        claim.manager_notified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(claim)
        return claim
    

def deactivate_claim_service(claim_id: int, request: Request, db: Session):
    tenant_id = get_tenant_id(request)

    db_claim = (
        db.query(Claim)
        .filter(Claim.id == claim_id, Claim.tenant_id == tenant_id)
        .first()
    )
    if not db_claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    # A claim cannot be deleted once its payment pack has been generated/raised.
    pack = (
        db.query(ABIBHRCharges)
        .filter(
            ABIBHRCharges.claim_id == claim_id,
            ABIBHRCharges.is_deleted == False,
            ABIBHRCharges.payment_pack_raised_date.isnot(None),
        )
        .first()
    )
    if pack:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This claim cannot be deleted because its payment pack has already been generated.",
        )

    # Soft delete — record is kept for possible restore, hidden everywhere.
    db_claim.is_active = False
    db_claim.is_deleted = True
    db.commit()
    db.refresh(db_claim)

    return {"detail": "Claim deactivated successfully"}


def restore_claim_service(claim_id: int, request: Request, db: Session):
    """Restore a soft-deleted (inactive) claim back to active."""
    tenant_id = get_tenant_id(request)
    db_claim = (
        db.query(Claim)
        .filter(Claim.id == claim_id, Claim.tenant_id == tenant_id)
        .first()
    )
    if not db_claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    db_claim.is_active = True
    db_claim.is_deleted = False
    db.commit()
    db.refresh(db_claim)
    return {"detail": "Claim restored successfully"}

def list_claim_detail(tenant_id :int , db: Session):
    claims = (
        db.query(Claim)
        .options(
            joinedload(Claim.case_status),
            joinedload(Claim.claim_type),
            joinedload(Claim.handler),
            joinedload(Claim.created_by_user),
        )
        .filter(Claim.tenant_id == tenant_id, Claim.is_active == True)
        .order_by(Claim.file_opened_at.desc())
        .all()
    )

    results = []
    ids = [c.id for c in claims]

    # Batch-load related rows ONCE (this used to run ~20 queries per claim, which
    # timed out once the claim count grew). One query per table, keyed by claim.
    def _first_by_claim(query):
        out = {}
        for r in query.all():
            out.setdefault(r.claim_id, r)
        return out

    _clients = _first_by_claim(
        db.query(ClientDetail).filter(
            ClientDetail.claim_id.in_(ids),
            ClientDetail.role == PersonRoleEnum.CLIENT,
        )
    )
    _addr_ids = [c.address_id for c in _clients.values() if c.address_id]
    _addresses = (
        {a.id: a for a in db.query(Address).filter(Address.id.in_(_addr_ids)).all()}
        if _addr_ids else {}
    )
    _accidents = _first_by_claim(
        db.query(LocationCondition).filter(LocationCondition.claim_id.in_(ids))
    )
    _client_vehicles = _first_by_claim(
        db.query(VehicleDetail)
        .options(joinedload(VehicleDetail.vehicle_status))
        .filter(VehicleDetail.claim_id.in_(ids))
    )
    _hires = {}
    for _h in (
        db.query(HireVehicleProvided)
        .options(joinedload(HireVehicleProvided.actual_vehicle_category))
        .filter(HireVehicleProvided.claim_id.in_(ids))
        .order_by(HireVehicleProvided.claim_id, HireVehicleProvided.id.desc())
        .all()
    ):
        _hires.setdefault(_h.claim_id, _h)  # highest id per claim

    # Latest update = max(updated_at) across the claim's related tables — computed
    # with one grouped query per table instead of loading every row per claim.
    _latest = {c.id: c.updated_at for c in claims}
    for _M in (
        ClientDetail, LocationCondition, Referrer, VehicleDetail, PoliceDetail,
        EngineerDetail, RouteRepair, TotalLoss, InsurerBroker, PanelSolicitor,
        Storage, Recovery, ThirdPartyInsurer, HireDetail, DriverDocumentAgreement,
        DriverCheck, HireVehicleProvided,
    ):
        for _cid, _mx in (
            db.query(_M.claim_id, func.max(_M.updated_at))
            .filter(_M.claim_id.in_(ids))
            .group_by(_M.claim_id)
            .all()
        ):
            if _mx is not None and (_latest.get(_cid) is None or _mx > _latest[_cid]):
                _latest[_cid] = _mx

    for claim in claims:
        client = _clients.get(claim.id)
        addr = _addresses.get(client.address_id) if (client and client.address_id) else None
        mobile_tel = (addr.mobile_tel or "") if addr else ""
        accident = _accidents.get(claim.id)
        client_vehicle = _client_vehicles.get(claim.id)
        hire = _hires.get(claim.id)

        actual_category = ""
        if hire and hire.actual_vehicle_category:
            actual_category = hire.actual_vehicle_category.label

        handler = handler_name_for_claim(claim, db) or (claim.handler.label if claim.handler else "")

        case_status = claim.case_status.label if claim.case_status else ""

        latest_update = _latest.get(claim.id)
        latest_update_str = latest_update.strftime('%d-%m-%Y %H:%M') if latest_update else None
        incident_date = accident.date_time  if accident else None
        # ---------------- PRIORITY LOGIC ----------------

        if case_status == "Claim Cancelled":
            priority = "Low"

        else:
            priority = "Medium"

            if incident_date is not None and incident_date.tzinfo is None:
                incident_date = incident_date.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)

            if incident_date is not None and (now - incident_date).days > 14:
                priority = "High"

            elif hire is None:
                priority = "High"

            elif client_vehicle and client_vehicle.vehicle_status and client_vehicle.vehicle_status.label.lower() == "not roadworthy":
                priority = "High"

        year = claim.file_opened_at.strftime("%Y") if claim.file_opened_at else datetime.now().strftime("%Y")
        month = claim.file_opened_at.strftime("%m") if claim.file_opened_at else datetime.now().strftime("%m")
        padded_id = str(claim.id).zfill(5)
        surname = client.surname if client else None
        our_reference = f"{surname}-{year}{month}-{padded_id}"

        results.append(
            ClaimListOut(
                claim_id=claim.id,
                our_reference=our_reference,
                client_name=f"{client.first_name} {surname}" if client else "",
                mobile_tel=mobile_tel,
                incident_date=incident_date,
                handler=handler,
                case_status=case_status,
                rejection_reason=claim.rejection_reason,
                actual_category=actual_category,
                claim_type=claim.claim_type.label if claim.claim_type else None,
                latest_update_str = f"{latest_update_str}",
                priority=priority,
                file_opened_at=claim.file_opened_at
        )
        )

    priority_order = {"High": 1, "Medium": 2, "Low": 3}
    results = sorted(results,key=lambda x: (priority_order.get(x.priority, 4),-x.file_opened_at.timestamp()))
    return results


def convert_claims_to_csv(records: list[ClaimListOut]) -> str:
    # CSV headers (matching ClaimListOut fields)
    fieldnames = [
        "Claim_Reference",
        "Client_Name",
        "Mobile_Tel",
        "Incident_Date",
        "Actual_Category",
        "Handler",
        "Case_Status",
        "Last_Updated_At",
        "Priority"
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for item in records:
        writer.writerow({
            "Claim_Reference": item.our_reference,
            "Client_Name": item.client_name,
            "Mobile_Tel": item.mobile_tel,
            "Incident_Date": item.incident_date.isoformat() if item.incident_date else "",
            "Actual_Category": item.actual_category,
            "Handler": item.handler,
            "Case_Status": item.case_status,
            "Last_Updated_At": item.latest_update_str,
            "Priority": item.priority,
        })

    return output.getvalue()
