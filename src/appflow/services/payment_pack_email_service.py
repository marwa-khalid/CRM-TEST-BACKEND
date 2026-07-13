import base64
import html
import os
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    Cc,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
    ReplyTo,
)
from sqlalchemy.orm import Session

from appflow.utils import build_case_reference, build_invoice_reference
from libdata.models.tables import ABIBHRCharges, Claim


FROM_EMAIL = os.getenv("SENDGRID_SENDER", "no-replynationwideassist@outlook.com")
REPLY_TO_EMAIL = os.getenv("SENDGRID_REPLY_TO", FROM_EMAIL)


def _split_emails(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [
        email.strip()
        for email in value.replace(",", ";").split(";")
        if email.strip()
    ]


def _html_body(case_reference: str, body: Optional[str]) -> str:
    message = body.strip() if body and body.strip() else (
        "Please find the requested payment pack document attached."
    )
    escaped_message = html.escape(message).replace("\n", "<br />")
    escaped_ref = html.escape(case_reference)

    return f"""
    <div style="font-family:Arial,sans-serif;color:#101828;font-size:14px;line-height:1.6;">
      <p>Hi,</p>
      <p>{escaped_message}</p>
      <p><strong>Case reference:</strong> {escaped_ref}</p>
      <p>Kind regards,<br />Nationwide Assist</p>
    </div>
    """


def _mark_pack_sent(
    db: Session,
    claim_id: int,
    current_user: int,
    sent_date: date,
) -> ABIBHRCharges:
    record = (
        db.query(ABIBHRCharges)
        .filter(
            ABIBHRCharges.claim_id == claim_id,
            ABIBHRCharges.is_active == True,
            ABIBHRCharges.is_deleted == False,
        )
        .first()
    )

    if not record:
        record = ABIBHRCharges(
            claim_id=claim_id,
            invoice_number=build_invoice_reference(claim_id),
            payment_pack_raised_date=sent_date,
            payment_pack_sent_date=sent_date,
            created_by=current_user,
            updated_by=current_user,
        )
        db.add(record)
    else:
        if not record.invoice_number:
            record.invoice_number = build_invoice_reference(claim_id)
        if not record.payment_pack_raised_date:
            record.payment_pack_raised_date = sent_date
        record.payment_pack_sent_date = sent_date
        record.updated_by = current_user

    db.commit()
    db.refresh(record)
    return record


def send_payment_pack_email(
    *,
    db: Session,
    claim_id: int,
    tenant_id: int,
    current_user: int,
    to_email: str,
    cc_email: Optional[str],
    subject: Optional[str],
    body: Optional[str],
    attachment_bytes: bytes,
    attachment_name: str,
    attachment_content_type: Optional[str],
):
    claim = (
        db.query(Claim)
        .filter(Claim.id == claim_id, Claim.tenant_id == tenant_id)
        .first()
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    recipients = _split_emails(to_email)
    if not recipients:
        raise HTTPException(status_code=400, detail="Recipient email is missing")

    cc_recipients = _split_emails(cc_email)
    if not attachment_bytes:
        raise HTTPException(status_code=400, detail="Attachment is missing")

    case_reference = build_case_reference(claim_id, db)
    clean_subject = (subject or "").strip() or f"Payment Pack - {case_reference}"
    clean_filename = (attachment_name or "Payment-Pack.pdf").strip()
    content_type = attachment_content_type or "application/pdf"

    # Graph-first so it reaches Outlook (logo auto-attached via cid:companylogo);
    # SendGrid fallback.
    from appflow.services.email_delivery import send_email as deliver_email

    result = deliver_email(
        to=recipients,
        cc=cc_recipients,
        subject=clean_subject,
        html=_html_body(case_reference, body),
        attachments=[{
            "name": clean_filename,
            "content_bytes": base64.b64encode(attachment_bytes).decode(),
            "content_type": content_type,
        }],
        reply_to=REPLY_TO_EMAIL,
    )
    if result.get("status") != "sent":
        raise HTTPException(status_code=502, detail=f"Email send failed: {result.get('detail')}")

    sent_date = date.today()
    record = _mark_pack_sent(db, claim_id, current_user, sent_date)

    return {
        "status": "success",
        "message": f"Payment pack email sent to {', '.join(recipients)}",
        "sendgrid_status": response.status_code,
        "payment_pack_sent_date": record.payment_pack_sent_date,
    }
