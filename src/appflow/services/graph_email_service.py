import base64
import os
from typing import List, Optional, Union

import requests

from appflow.logger import logger
from appflow.services.microsoft_graph_token_service import MicrosoftGraphTokenService

# Load the company logo once so it can be attached inline (cid:companylogo).
# Emails reference the logo as <img src="cid:companylogo">; attaching it inline
# means it always renders (no dependency on an external image host).
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "logo.png")
try:
    with open(_LOGO_PATH, "rb") as _lf:
        _LOGO_B64 = base64.b64encode(_lf.read()).decode()
except Exception:
    _LOGO_B64 = ""


class _GraphSendResult:
    """Minimal response shim so callers can check ``.status_code`` the same way
    they do for a SendGrid/requests response."""

    def __init__(self, status_code: int):
        self.status_code = status_code


def _to_recipients(value: Union[str, List[str], None]) -> List[dict]:
    """Normalize a string ("a@b.com;c@d.com" / comma-separated) or list into the
    Graph ``emailAddress`` recipient shape, dropping anything without an ``@``."""
    if not value:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(",", ";").split(";")]
    else:
        parts = [str(p).strip() for p in value]
    seen, out = set(), []
    for p in parts:
        if p and "@" in p and p.lower() not in seen:
            seen.add(p.lower())
            out.append({"emailAddress": {"address": p}})
    return out


class GraphEmailService:
    """Send email from the connected Outlook mailbox via Microsoft Graph.

    Sending through Graph means mail leaves from a *real* Outlook mailbox
    (marwanationwideassist@outlook.com), so it is actually delivered — unlike
    SendGrid from the unverified yopmail.com sender, which strict providers
    (Outlook in particular) silently drop.
    """

    GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
    _last_error = ""

    @classmethod
    def last_error(cls) -> str:
        return cls._last_error

    @classmethod
    def _set_error(cls, detail: str) -> None:
        cls._last_error = detail

    @staticmethod
    def is_configured() -> bool:
        """True if we have credentials to obtain a delegated Graph token."""
        return bool(
            os.getenv("MS_GRAPH_SEND_REFRESH_TOKEN")
            or os.getenv("MS_GRAPH_EMAIL_REFRESH_TOKEN")
            or os.getenv("OUTLOOK_SEND_REFRESH_TOKEN")
            or os.getenv("MS_GRAPH_SEND_ACCESS_TOKEN")
            or os.getenv("OUTLOOK_SEND_ACCESS_TOKEN")
        )

    @classmethod
    def send_mail(
        cls,
        to: Union[str, List[str]],
        subject: str,
        html_content: str,
        cc: Union[str, List[str], None] = None,
        reply_to: Union[str, List[str], None] = None,
        inline_images: Optional[List[dict]] = None,
        attachments: Optional[List[dict]] = None,
    ) -> Optional[_GraphSendResult]:
        """Best-effort send. Returns a result with ``.status_code`` (202 on
        success) or ``None`` if it could not be sent (so callers can fall back).

        ``inline_images`` is an optional list of extra inline attachments, each a
        dict ``{"cid": str, "content_bytes": <base64 str>, "content_type": str,
        "name": <optional str>}`` referenced in the HTML as ``cid:<cid>``.

        ``attachments`` is an optional list of regular (non-inline) file
        attachments, each a dict ``{"name": str, "content_bytes": <base64 str>,
        "content_type": str}``.
        """
        to_recipients = _to_recipients(to)
        cc_recipients = _to_recipients(cc)
        cls._set_error("")
        if not to_recipients and not cc_recipients:
            detail = "no valid recipients"
            cls._set_error(detail)
            logger.warning(f"Graph send skipped: {detail}")
            return None

        token = MicrosoftGraphTokenService.get_access_token("send")
        if not token:
            detail = "no access token available"
            cls._set_error(detail)
            logger.warning(f"Graph send skipped: {detail}")
            return None

        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_content},
            "toRecipients": to_recipients or cc_recipients,
        }
        if to_recipients and cc_recipients:
            message["ccRecipients"] = cc_recipients
        reply_to_recipients = _to_recipients(reply_to)
        if reply_to_recipients:
            message["replyTo"] = reply_to_recipients

        graph_attachments: List[dict] = []
        # Attach the logo inline whenever the HTML references it, so cid:companylogo renders.
        if _LOGO_B64 and "cid:companylogo" in (html_content or ""):
            graph_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": "logo.png",
                "contentType": "image/png",
                "contentBytes": _LOGO_B64,
                "contentId": "companylogo",
                "isInline": True,
            })
        # Any extra inline images (e.g. checkout photos).
        for img in (inline_images or []):
            if not img.get("cid") or not img.get("content_bytes"):
                continue
            graph_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": img.get("name") or f"{img['cid']}.jpg",
                "contentType": img.get("content_type", "image/jpeg"),
                "contentBytes": img["content_bytes"],
                "contentId": img["cid"],
                "isInline": True,
            })
        # Regular (non-inline) file attachments, e.g. document-library files.
        for att in (attachments or []):
            if not att.get("content_bytes"):
                continue
            graph_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": att.get("name") or "attachment",
                "contentType": att.get("content_type", "application/octet-stream"),
                "contentBytes": att["content_bytes"],
                "isInline": False,
            })
        if graph_attachments:
            message["attachments"] = graph_attachments

        try:
            resp = requests.post(
                cls.GRAPH_SEND_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"message": message, "saveToSentItems": True},
                timeout=30,
            )
            if resp.status_code in (200, 202):
                addrs = [r["emailAddress"]["address"] for r in to_recipients]
                logger.info(f"Graph email sent to {addrs}")
                return _GraphSendResult(resp.status_code)
            cls._set_error(f"status={resp.status_code} body={resp.text[:300]}")
            logger.warning(
                f"Graph send failed: status={resp.status_code} body={resp.text[:300]}"
            )
            return None
        except Exception as e:
            cls._set_error(str(e))
            logger.warning(f"Graph send error: {e}")
            return None
