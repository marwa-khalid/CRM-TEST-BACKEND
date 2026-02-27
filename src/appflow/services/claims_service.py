# app/services/claims_service.py
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from fastapi import BackgroundTasks, HTTPException, status,Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from libdata.models.tables import (Claim, SourceChannel, User)
from appflow.utils import get_tenant_id
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To, ReplyTo
from datetime import datetime, timezone
def _labels_bundle(c: Claim) -> Dict[str, Any]:
    return {
        "claim_type": c.claim_type.label if c.claim_type else None,
        "handler": c.handler.label if c.handler else None,
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
        user = db.get(User, staff_user_id)
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected staff user is invalid or inactive.")


def _validate_abroad(payload: Dict[str, Any]):
    if payload.get("client_going_abroad") and not payload.get("abroad_date"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "abroad_date is required when client_going_abroad is true.")


# def _send_email(to_list: List[str], subject: str, body: str):
#     # TODO: integrate with your mailer (SES/SMTP/etc.)
#     # This is a stub to keep the service side-effect in one place.
#     return

def _send_email(recipients: list, subject: str, html_content: str):
    message = Mail(
        from_email="No-Reply <noreplynationwideassist@yopmail.com>", # Format: "Name <email>"
        to_emails=[To(email) for email in recipients],
        subject=subject,
        html_content=html_content
    )
    print("working")
    # Optional: Explicitly tell mail clients where replies should NOT go
    message.reply_to = ReplyTo("noreplynationwideassist@yopmail.com", "No-Reply")
    print(os.getenv("SENDGRID_API_KEY"))
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        print("working")
        sg.send(message)
        print(message)
    except Exception as e:
        print(f"Error: {e}")
# ---------- CRUD ----------

def create_claim(db: Session, payload: Dict[str, Any], current_user_id: int, tenant_id: int) -> Claim:
    _validate_abroad(payload)
    _require_staff_if_needed(db, payload.get("source_id"), payload.get("source_staff_user_id"))

    claim = Claim(**payload)
    claim.entrant_user_id = current_user_id  # who opened the file (username shown in UI via User)
    claim.tenant_id = tenant_id
    db.add(claim)
    db.commit()  # assign PK
    db.refresh(claim)
    # claim.labels = _labels_bundle(claim)  # type: ignore[attr-defined]
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
            c.handler_id, h.label AS handler_label,
            c.target_debt_id, td.label AS target_debt_label,
            c.case_status_id, cs.label AS case_status_label,
            c.source_id, s.label AS source_label,
            c.source_staff_user_id, ss.first_name || ' ' || ss.last_name AS source_staff_label,  -- Staff user name
            c.prospects_id, p.label AS prospect_label,
            c.present_position_id, pfp.label AS present_position_label,
            c.credit_hire_accepted, c.non_fault_accident, c.any_passengers,
            c.client_injured, c.file_opened_at, c.file_closed_at, c.file_closed_reason, c.is_locked,
            c.client_going_abroad, c.abroad_date, c.manager_notified_at
        FROM claims c
        LEFT JOIN claim_types ct ON c.claim_type_id = ct.id
        LEFT JOIN handlers h ON c.handler_id = h.id
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


def update_claim(db: Session, claim_id: int, payload: Dict[str, Any]) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found.")
    if claim.is_locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Claim is closed/locked.")

    # validations
    merged = {**{k: getattr(claim, k) for k in [
        "source_id", "source_staff_user_id", "client_going_abroad", "abroad_date"
    ]}, **payload}
    _validate_abroad(merged)
    _require_staff_if_needed(db, merged.get("source_id"), merged.get("source_staff_user_id"))

    for k, v in payload.items():
        setattr(claim, k, v)

    db.commit()
    db.refresh(claim)
    # claim.labels = _labels_bundle(claim)  # type: ignore[attr-defined]
    return claim


def close_claim(db: Session, claim_id: int, reason: str) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found.")
    if claim.is_locked:
        return claim
    if not reason or not reason.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Closure reason is required.")

    claim.file_closed_reason = reason.strip()
    claim.file_closed_at = datetime.now(timezone.utc)
    # claim.is_locked = True

    db.commit()
    db.refresh(claim)
    # claim.labels = _labels_bundle(claim)  # type: ignore[attr-defined]
    return claim


# def notify_manager(db: Session, claim_id: int, note: Optional[str]) -> Claim:
#     claim = db.get(Claim, claim_id)
#     if not claim:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found.")
#     if not claim.client_going_abroad or not claim.abroad_date:
#         raise HTTPException(status.HTTP_400_BAD_REQUEST,
#                             "Set 'client_going_abroad' and 'abroad_date' before notifying.")

#     # setting = (db.query(SystemSetting)
#     #              .filter(SystemSetting.key == "claims_fleet_group_emails")
#     #              .first())
#     # recipients = []
#     # if setting and setting.value:
#     #     recipients = setting.value.get("emails", []) or []

#     subject = f"[Claims] Client going abroad – Case #{claim.id}"
#     body = f"Case #{claim.id}\nAbroad Date: {claim.abroad_date}\nNote: {note or ''}"
#     # _send_email(recipients, subject, body)

#     claim.manager_notified_at = datetime.now(timezone.utc)
#     db.commit()
#     db.refresh(claim)
#     #claim.labels = _labels_bundle(claim)  # type: ignore[attr-defined]
#     return claim

def notify_manager(db: Session, claim_id: int,recipient:str, background_tasks: BackgroundTasks) -> Claim:
    claim = db.get(Claim, claim_id)
    # ... (Your existing validation logic) ...

    # Pull list from your system settings
    recipients = [recipient]
    formatted_now = datetime.now().strftime("%d-%m-%y")
    subject = "Notification of Vulnerable Person"
    year_month = datetime.now().strftime("%Y%m")

     # 2. Your case number
    # 3. Combine with 4-digit padding
    case_id = f"{year_month}-{claim.id:04d}"
    # The Template from your image
    # Note: If possible, swap this .svg for a .png URL for better compatibility
    logo_url = "https://image2url.com/r2/default/images/1772144213817-5641d8a2-de81-4933-b96d-838f8644d636.svg"

    html_body = f"""
    <html>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: Arial, sans-serif;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff;">
            <tr>
                <td align="center" style="padding: 40px 20px;">
                    
                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                        <tr>
                            <td align="center">
                                <img src="{logo_url}" alt="Nationwide Assist" width="200" style="display: block; border: 0; outline: none; text-decoration: none;">
                            </td>
                        </tr>
                    </table>

                    <table width="100%" border="0" cellspacing="0" cellpadding="16" style="max-width: 380px; border: 1px solid #CCCCCC; border-radius: 8px; background-color: #ffffff;">
                        <tr>
                            <td>
                                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                    <tr>
                                        <td width="136" style="color: #444444; font-size: 12px; font-weight: 400;">Case No:</td>
                                        <td style="color: #444444; font-size: 12px; font-weight: 600;">{case_id}</td>
                                    </tr>
                                    <tr><td colspan="2" style="height: 8px;"></td></tr>
                                    <tr><td colspan="2" style="height: 1px; background-color: #CCCCCC;"></td></tr>
                                    <tr><td colspan="2" style="height: 8px;"></td></tr>
                                    <tr>
                                        <td width="136" style="color: #444444; font-size: 12px; font-weight: 400;">Client Name:</td>
                                        <td style="color: #444444; font-size: 12px; font-weight: 600;">{claim.client_name if hasattr(claim, 'client_name') else 'N/A'}</td>
                                    </tr>
                                    <tr><td colspan="2" style="height: 8px;"></td></tr>
                                    <tr><td colspan="2" style="height: 1px; background-color: #CCCCCC;"></td></tr>
                                    <tr><td colspan="2" style="height: 8px;"></td></tr>
                                    <tr>
                                        <td width="136" style="color: #444444; font-size: 12px; font-weight: 400;">Date:</td>
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

    # Database updates
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

    db_claim.is_active = False
    db_claim.is_deleted = True
    db.commit()
    db.refresh(db_claim)

    return {"detail": "Claim deactivated successfully"}
