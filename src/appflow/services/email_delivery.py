import os
from typing import List, Optional, Union

from appflow.logger import logger
from appflow.services.graph_email_service import GraphEmailService


def _split_recipients(to: Union[str, List[str], None]) -> List[str]:
    if not to:
        return []
    if isinstance(to, str):
        parts = [e.strip() for e in to.replace(",", ";").split(";")]
    else:
        parts = [str(e).strip() for e in to]
    return [e for e in parts if e and "@" in e]


def _is_microsoft_mailbox(value: Optional[str]) -> bool:
    email = (value or "").strip().lower()
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1]
    return domain in {"outlook.com", "hotmail.com", "live.com", "msn.com"}


def _env_bool(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def send_email(
    to: Union[str, List[str]],
    subject: str,
    html: str,
    attachments: Optional[List[dict]] = None,
    cc: Union[str, List[str], None] = None,
    from_email: Optional[str] = None,
    reply_to: Union[str, List[str], None] = None,
) -> dict:
    """Deliver an email Microsoft-Graph-first, SendGrid as fallback.

    Sending via Graph means mail leaves from the connected Outlook mailbox, so it
    actually reaches Outlook (SendGrid from the unverified yopmail.com sender is
    silently dropped by strict providers). Use this everywhere instead of calling
    SendGrid directly.

    ``attachments`` is a list of ``{"name": str, "content_bytes": <base64 str>,
    "content_type": str}`` (and optional ``"cid"`` + inline handling is done by
    GraphEmailService when the HTML references ``cid:``).
    """
    recipients = _split_recipients(to)
    if not recipients:
        logger.warning("send_email skipped: no valid recipients")
        return {"status": "skipped", "detail": "no valid recipients"}

    sender = (
        from_email
        or os.getenv("SENDGRID_SENDER", "no-replynationwideassist@outlook.com")
    )

    # Prefer Graph.
    graph_configured = GraphEmailService.is_configured()
    if graph_configured:
        result = GraphEmailService.send_mail(
            recipients, subject, html, cc=cc, reply_to=reply_to, attachments=attachments
        )
        if result is not None:
            return {"status": "sent", "via": "graph"}
        graph_detail = GraphEmailService.last_error() or "unknown Graph error"
        if _env_bool("EMAIL_DELIVERY_REQUIRE_GRAPH") or _is_microsoft_mailbox(sender):
            logger.warning(
                "Graph send failed; SendGrid fallback skipped because sender "
                f"{sender} must be sent through Microsoft Graph: {graph_detail}"
            )
            return {
                "status": "failed",
                "detail": (
                    "Microsoft Graph send failed: "
                    f"{graph_detail}. SendGrid fallback skipped because {sender} "
                    "is an Outlook/Microsoft mailbox sender."
                ),
            }
        logger.warning(f"Graph send failed; falling back to SendGrid: {graph_detail}")

    # SendGrid fallback.
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, Attachment, FileContent, FileName, FileType, Disposition, To,
        )
        api_key = os.getenv("SENDGRID_API_KEY")
        if not api_key:
            return {"status": "skipped", "detail": "email not configured"}
        message = Mail(
            from_email=sender,
            to_emails=[To(e) for e in recipients],
            subject=subject,
            html_content=html,
        )
        for cc_email in _split_recipients(cc):
            message.add_cc(cc_email)
        for att in (attachments or []):
            if not att.get("content_bytes"):
                continue
            message.add_attachment(Attachment(
                FileContent(att["content_bytes"]),
                FileName(att.get("name") or "attachment"),
                FileType(att.get("content_type") or "application/octet-stream"),
                Disposition("attachment"),
            ))
        resp = SendGridAPIClient(api_key).send(message)
        return {"status": "sent", "via": "sendgrid", "sendgrid_status": resp.status_code}
    except Exception as exc:
        logger.warning(f"send_email failed for {recipients}: {exc}")
        return {"status": "failed", "detail": str(exc)}
