"""Fleet outbound email — free-form subject/message with arbitrary attachments.

Reuses the host app's Graph-first delivery via the ``send_email`` seam in
``fleet.deps`` so Fleet stays independent of Claims code.
"""
import base64
from typing import List, Optional

from fleet.deps import send_email


def build_attachment(filename: Optional[str], content_type: Optional[str], content: bytes) -> dict:
    return {
        "name": filename or "attachment",
        "content_bytes": base64.b64encode(content).decode("ascii"),
        "content_type": content_type or "application/octet-stream",
    }


def send_hire_email(
    to: str,
    subject: str,
    body: str,
    attachments: Optional[List[dict]] = None,
    cc: Optional[str] = None,
) -> dict:
    # Plain-text body -> minimal HTML that preserves the user's line breaks.
    safe = (body or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = f'<div style="white-space:pre-wrap;font-family:sans-serif">{safe}</div>'
    return send_email(to=to, subject=subject or "", html=html, attachments=attachments or [], cc=cc)
