"""Parse a dragged-in email file (.eml via the stdlib, .msg via extract-msg)
into a normalised dict for the Case History import."""
import base64
import email
import email.policy
import os
import re
import tempfile
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import List, Optional


def _split_addresses(raw: str) -> List[str]:
    if not raw:
        return []
    # Recipients come separated by "," or ";" depending on the source.
    parts: List[str] = []
    for chunk in raw.replace(";", ",").split(","):
        addr = parseaddr(chunk)[1]
        if addr:
            parts.append(addr)
    return parts


def _parse_eml(data: bytes) -> dict:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    from_name, from_email = parseaddr(msg.get("from") or "")
    dt: Optional[datetime] = None
    try:
        dt = parsedate_to_datetime(msg.get("date")) if msg.get("date") else None
    except Exception:
        dt = None

    body_text, body_html = "", ""
    attachments: List[dict] = []
    cid_map: dict = {}  # content-id -> data: URI (inline signature images)
    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        ctype = part.get_content_type()
        filename = part.get_filename()
        cid = (part.get("Content-ID") or "").strip().strip("<>").strip()
        # Inline images (Outlook signature logo / social icons) — bundle them into
        # the body as data: URIs instead of listing them as attachments, so the
        # signature renders exactly like the original email.
        is_inline_img = ctype.startswith("image/") and (bool(cid) or disposition == "inline")
        if is_inline_img:
            if cid:
                payload = part.get_payload(decode=True) or b""
                if payload:
                    cid_map[cid] = f"data:{ctype};base64,{base64.b64encode(payload).decode('ascii')}"
            continue
        if disposition == "attachment" or filename:
            payload = part.get_payload(decode=True) or b""
            attachments.append({
                "name": filename or "attachment",
                "data": payload,
                "content_type": ctype or "application/octet-stream",
            })
        elif ctype == "text/plain" and not body_text:
            try:
                body_text = part.get_content()
            except Exception:
                body_text = ""
        elif ctype == "text/html" and not body_html:
            try:
                body_html = part.get_content()
            except Exception:
                body_html = ""

    # Swap each cid: reference in the HTML for its inlined data: URI.
    if body_html and cid_map:
        for _cid, _uri in cid_map.items():
            body_html = re.sub(r"cid:" + re.escape(_cid), lambda _m: _uri, body_html, flags=re.IGNORECASE)

    return {
        "subject": msg.get("subject") or "",
        "from_name": from_name or "",
        "from_email": from_email or "",
        "to": _split_addresses(msg.get("to") or ""),
        "date": dt,
        "body_text": body_text or "",
        "body_html": body_html or "",
        "attachments": attachments,
    }


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "ignore")
        except Exception:
            return ""
    return str(value)


def _parse_msg(data: bytes) -> dict:
    import extract_msg

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tf:
            tf.write(data)
            tmp_path = tf.name
        m = extract_msg.Message(tmp_path)
        from_name, from_email = parseaddr(_as_text(m.sender))
        dt: Optional[datetime] = None
        raw_date = getattr(m, "date", None)
        if isinstance(raw_date, datetime):
            dt = raw_date
        elif raw_date:
            try:
                dt = parsedate_to_datetime(_as_text(raw_date))
            except Exception:
                dt = None

        attachments: List[dict] = []
        for att in (m.attachments or []):
            name = _as_text(getattr(att, "longFilename", "") or getattr(att, "shortFilename", "")) or "attachment"
            payload = getattr(att, "data", b"") or b""
            if isinstance(payload, str):
                payload = payload.encode("utf-8", "ignore")
            attachments.append({
                "name": name,
                "data": payload,
                "content_type": "application/octet-stream",
            })

        return {
            "subject": _as_text(m.subject),
            "from_name": from_name or "",
            "from_email": from_email or "",
            "to": _split_addresses(_as_text(m.to)),
            "date": dt,
            "body_text": _as_text(m.body),
            "body_html": _as_text(getattr(m, "htmlBody", "")),
            "attachments": attachments,
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# .msg files are OLE2 compound documents — they always start with this magic.
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def parse_email_bytes(filename: str, data: bytes) -> dict:
    """Return {subject, from_name, from_email, to[], date, body_text, body_html,
    attachments[{name,data,content_type}]} for a .eml or .msg file.

    Drag-and-drop from Outlook rarely hands us a clean ``.eml``/``.msg`` name — the
    dropped file may have no extension, or the subject as its name. So we sniff the
    bytes: an OLE2 header means it's a ``.msg``, anything else is parsed as MIME
    (``.eml``). The filename is only a fallback hint."""
    name = (filename or "").lower()
    if data[:8] == _OLE_MAGIC or name.endswith(".msg"):
        return _parse_msg(data)
    return _parse_eml(data)
