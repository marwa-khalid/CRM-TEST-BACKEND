"""
OutlookCaseActivityService
--------------------------
Fetches emails from Microsoft Graph API for a given case reference,
maps them into CaseActivityItemOut objects for the activity stream.

Also provides reply/forward helpers that return mailto: URLs so the
frontend can open Outlook pre-filled.

Important:
- Access tokens should come from MicrosoftGraphTokenService, not hardcoded source.
- For app-only Graph auth, configure MS_GRAPH_MAILBOX because /me is user-delegated only.
"""

import re
import html
import base64
import urllib.parse
from datetime import datetime
from typing import List, Optional, Tuple

import requests

from appflow.models.case_activity import (
    CaseActivityItemOut,
    CaseActivityAttachmentOut,
)
from appflow.services.microsoft_graph_token_service import MicrosoftGraphTokenService


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _mailbox_url(path: str = "", context: str = "read") -> str:
    mailbox = MicrosoftGraphTokenService.mailbox_user(context)
    if mailbox:
        base = f"{GRAPH_BASE}/users/{urllib.parse.quote(mailbox, safe='')}"
    else:
        base = f"{GRAPH_BASE}/me"

    clean_path = (path or "").lstrip("/")
    return f"{base}/{clean_path}" if clean_path else base


class OutlookCaseActivityService:
    # ------------------------------------------------------------------
    # Main entry: fetch emails matching a case reference
    # ------------------------------------------------------------------

    @staticmethod
    def get_case_emails(
        claim_reference: str,
        access_token: str,
    ) -> List[CaseActivityItemOut]:
        """
        Search the signed-in Outlook mailbox for emails containing
        the case reference. Returns mapped CaseActivityItemOut items.
        """

        print("INSIDE OUTLOOK get_case_emails")
        print("CLAIM REF RECEIVED:", claim_reference)
        print("ACCESS TOKEN EXISTS IN OUTLOOK SERVICE:", bool(access_token))

        if not access_token:
            print("NO OUTLOOK ACCESS TOKEN PROVIDED")
            return []

        messages = OutlookCaseActivityService._search_messages(
            claim_reference=claim_reference,
            access_token=access_token,
        )

        print("RAW OUTLOOK MESSAGES:", len(messages))

        items: List[CaseActivityItemOut] = []

        for msg in messages:
            item = OutlookCaseActivityService._map_message(msg)
            if item:
                items.append(item)

        print("MAPPED OUTLOOK EMAIL ITEMS:", len(items))

        return items

    # ------------------------------------------------------------------
    # Fetch ALL recent mailbox emails (all-cases activity view)
    # ------------------------------------------------------------------

    @staticmethod
    def get_all_emails(
        access_token: str,
        references: Optional[List[str]] = None,
        top: int = 50,
    ) -> List[CaseActivityItemOut]:
        """
        For the all-cases activity view: pull recent mailbox emails in ONE Graph
        call, then keep only those whose subject or body mentions at least one
        claim reference (any of Khalid-, Patel-, …). Emails that reference no
        claim are dropped. Pass references=None to skip filtering.
        """
        if not access_token:
            print("NO OUTLOOK ACCESS TOKEN PROVIDED (get_all_emails)")
            return []

        if references is not None:
            refs = [str(r).replace('"', "") for r in references if r]
            if not refs:
                return []
            # ONE Graph call: pull the most recent mailbox messages and keep only
            # those whose subject/body mentions a claim reference. This replaces a
            # per-20-reference $search that fired ~N/20 sequential Graph calls for
            # N claims (hundreds of claims => ~20+ slow calls) and made the
            # all-cases view "load and load".
            messages = OutlookCaseActivityService._list_recent_messages(
                access_token, top
            )
            refs_lower = [r.lower() for r in refs]
            messages = [
                m for m in messages
                if OutlookCaseActivityService._mentions_reference(m, refs_lower)
            ]
            print("EMAILS MATCHING A CLAIM REFERENCE:", len(messages))
        else:
            messages = OutlookCaseActivityService._list_recent_messages(access_token, top)

        items: List[CaseActivityItemOut] = []
        for msg in messages:
            # Fetch attachment metadata only for the emails we're keeping.
            if msg.get("hasAttachments"):
                msg["_attachments"] = OutlookCaseActivityService._get_attachments(
                    message_id=msg.get("id", ""),
                    access_token=access_token,
                )
            else:
                msg["_attachments"] = []

            item = OutlookCaseActivityService._map_message(msg)
            if item:
                items.append(item)

        return items

    @staticmethod
    def _search_by_references(access_token: str, references: list, top: int = 50) -> list:
        """One (or a few chunked) Graph $search call(s) matching any claim
        reference — finds emails regardless of recency, unlike a recent list."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        url = _mailbox_url("messages")
        seen: dict = {}
        CHUNK = 20  # keep each $search expression within Graph's limits
        for i in range(0, len(references), CHUNK):
            chunk = references[i:i + CHUNK]
            search_val = " OR ".join(f'"{r}"' for r in chunk)
            params = {
                "$search": search_val,
                "$select": (
                    "id,subject,from,toRecipients,receivedDateTime,"
                    "bodyPreview,body,hasAttachments,webLink"
                ),
                "$top": str(top),
            }
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=20)
                print("GRAPH SEARCH-REFS STATUS:", resp.status_code)
                resp.raise_for_status()
                for m in resp.json().get("value", []):
                    mid = m.get("id")
                    if mid and mid not in seen:
                        seen[mid] = m
            except Exception as exc:
                print(f"[OutlookCaseActivityService] Ref search chunk failed: {exc}")

        print("GRAPH SEARCH-REFS UNIQUE:", len(seen))
        return list(seen.values())

    @staticmethod
    def _list_recent_messages(access_token: str, top: int = 50) -> list:
        """List recent mailbox messages ordered newest-first (no $search, no
        attachment enrichment — attachments are fetched later only for kept)."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = _mailbox_url("messages")
        params = {
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,"
                "bodyPreview,body,hasAttachments,webLink"
            ),
            "$top": str(top),
            "$orderby": "receivedDateTime desc",
        }

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)
            print("GRAPH LIST-ALL STATUS:", resp.status_code)
            resp.raise_for_status()
            messages = resp.json().get("value", [])
            print("GRAPH LIST-ALL COUNT:", len(messages))
            return messages
        except Exception as exc:
            print(f"[OutlookCaseActivityService] Graph list-all failed: {exc}")
            return []

    @staticmethod
    def _mentions_reference(msg: dict, references_lower: List[str]) -> bool:
        """True if the email subject/body contains any claim reference."""
        if not references_lower:
            return False
        body_obj = msg.get("body") or {}
        haystack = " ".join([
            msg.get("subject") or "",
            msg.get("bodyPreview") or "",
            body_obj.get("content") or "",
        ]).lower()
        return any(ref in haystack for ref in references_lower)


    @staticmethod
    def send_email_with_attachments_via_graph(
        to_email: str,
        subject: str,
        comment: str,
        attachments: list,
        access_token: str,
        is_html: bool = False,
    ) -> bool:
        import requests

        url = _mailbox_url("sendMail")

        payload = {
            "message": {
                "subject": subject or "Case Activity",
                "body": {
                    "contentType": "HTML" if is_html else "Text",
                    "content": comment or "",
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email,
                        }
                    }
                ],
                "attachments": attachments or [],
            },
            "saveToSentItems": True,
        }

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

        if response.status_code not in (200, 202):
            print(
                "[OutlookCaseActivityService] Send mail failed:",
                response.status_code,
                response.text,
            )
            return False

        return True
    # ------------------------------------------------------------------
    # Graph API: search messages by case reference
    # ------------------------------------------------------------------

    @staticmethod
    def _search_messages(claim_reference: str, access_token: str) -> list:
        """
        Uses Microsoft Graph /me/messages with $search.

        This searches the signed-in user's Outlook mailbox for the
        case reference, e.g. Dean-202603-00004.
        """

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        safe_ref = (claim_reference or "").replace('"', "").strip()

        if not safe_ref:
            print("EMPTY CLAIM REFERENCE, SKIPPING OUTLOOK SEARCH")
            return []

        # First print which Outlook account this token belongs to
        try:
            profile_resp = requests.get(
                _mailbox_url(),
                headers=headers,
                timeout=10,
            )

            print("OUTLOOK PROFILE STATUS:", profile_resp.status_code)
            print("OUTLOOK PROFILE:", profile_resp.text[:2000])

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Outlook profile check failed: {exc}")

        url = _mailbox_url("messages")

        params = {
            "$search": f'"{safe_ref}"',
            "$select": (
                "id,subject,from,toRecipients,receivedDateTime,"
                "bodyPreview,body,hasAttachments,webLink"
            ),
            "$top": "50",
        }

        try:
            resp = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=20,
            )

            print("GRAPH SEARCH URL:", resp.url)
            print("GRAPH SEARCH STATUS:", resp.status_code)
            print("GRAPH SEARCH RESPONSE:", resp.text[:3000])

            resp.raise_for_status()

            data = resp.json()
            messages = data.get("value", [])

            print("GRAPH MESSAGE COUNT:", len(messages))

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Graph search failed: {exc}")
            return []

        enriched = []

        for msg in messages:
            if msg.get("hasAttachments"):
                msg["_attachments"] = OutlookCaseActivityService._get_attachments(
                    message_id=msg.get("id", ""),
                    access_token=access_token,
                )
            else:
                msg["_attachments"] = []

            enriched.append(msg)

        return enriched

    # ------------------------------------------------------------------
    # Graph API: get attachment metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _get_attachments(message_id: str, access_token: str) -> list:
        """
        Fetch file attachment metadata for a single Outlook message.
        """

        if not message_id:
            return []

        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        url = _mailbox_url(f"messages/{message_id}/attachments")

        params = {
            "$select": "id,name,contentType,size",
        }

        try:
            resp = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=15,
            )

            print("ATTACHMENTS STATUS:", resp.status_code)
            print("ATTACHMENTS RESPONSE:", resp.text[:1000])

            resp.raise_for_status()

            return resp.json().get("value", [])

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Attachment fetch failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Mapping: Graph message → CaseActivityItemOut
    # ------------------------------------------------------------------

    @staticmethod
    def _map_message(msg: dict) -> Optional[CaseActivityItemOut]:
        try:
            subject = msg.get("subject") or "(No Subject)"

            from_info = msg.get("from", {}).get("emailAddress", {})
            sender_name = from_info.get("name") or ""
            sender_email = from_info.get("address") or ""

            received_str = msg.get("receivedDateTime") or ""
            received_at: Optional[datetime] = None

            if received_str:
                received_at = datetime.fromisoformat(
                    received_str.replace("Z", "+00:00")
                )

            body_preview = msg.get("bodyPreview") or ""

            body_obj = msg.get("body") or {}
            body_html = ""
            body_text = body_obj.get("content") or ""
            body_content_type = body_obj.get("contentType") or "text"

            if body_content_type.lower() == "html":
                body_html = body_text
                body_text = OutlookCaseActivityService._strip_html(body_text)

            # if body_content_type.lower() == "html":
            #     body_text = OutlookCaseActivityService._strip_html(body_text)

            attachments: List[CaseActivityAttachmentOut] = []

            for att in msg.get("_attachments", []):
                att_name = att.get("name") or "Attachment"
                att_id = att.get("id") or ""
                msg_id = msg.get("id") or ""

                if not att_id or not msg_id:
                    continue

                file_url = (
                    f"/case-activity/email-attachment/"
                    f"{urllib.parse.quote(msg_id, safe='')}/"
                    f"{urllib.parse.quote(att_id, safe='')}"
                )

                attachments.append(
                    CaseActivityAttachmentOut(
                        file_name=att_name,
                        file_url=file_url,
                        file_size=OutlookCaseActivityService._format_size(
                            att.get("size")
                        ),
                        case_document_id=None,
                    )
                )

            outlook_web_link = msg.get("webLink") or ""

            return CaseActivityItemOut(
                id=msg.get("id") or "",
                type="Email",
                history_file_type="outlook_email",
                title=subject,
                timestamp=received_at,
                summary="",
                detail_text="",
                created_by_name=sender_name,
                attachments=attachments,
                subject=subject,
                sender_name=sender_name,
                sender_email=sender_email,
                received_at=received_at,
                body_preview=body_preview,
                body_text=body_text,
                body_html=body_html,
                meta={
                    "source_type": "outlook_email",
                    "message_id": msg.get("id") or "",
                    "web_link": outlook_web_link,
                    "has_attachments": bool(msg.get("hasAttachments")),
                },
            )

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Mapping failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Reply helper — opens mail app
    # ------------------------------------------------------------------

    @staticmethod
    def build_reply_mailto(
        sender_email: str,
        subject: str,
        body_text: str = "",
    ) -> str:
        """
        Builds a mailto URL for reply.
        Note: mailto cannot truly reply inside the original Outlook thread.
        For true threaded reply, use reply_via_graph().
        """

        safe_subject = subject or ""
        reply_subject = (
            safe_subject
            if safe_subject.lower().startswith("re:")
            else f"Re: {safe_subject}"
        )

        quoted_body = ""

        if body_text:
            quoted_body = "\n\n--- Original Message ---\n" + body_text

        params = urllib.parse.urlencode(
            {
                "subject": reply_subject,
                "body": quoted_body,
            }
        )

        return f"mailto:{urllib.parse.quote(sender_email or '')}?{params}"

    # ------------------------------------------------------------------
    # Forward helper — opens mail app
    # ------------------------------------------------------------------

    @staticmethod
    def build_forward_mailto(
        subject: str,
        body_text: str = "",
        attachment_names: Optional[List[str]] = None,
    ) -> str:
        """
        Builds a mailto URL for forwarding.

        Important:
        mailto cannot attach files automatically.
        It can only put attachment names in the body.
        For true forwarding with attachments, use forward_via_graph().
        """

        safe_subject = subject or ""
        fwd_subject = (
            safe_subject
            if safe_subject.lower().startswith("fwd:")
            else f"Fwd: {safe_subject}"
        )

        fwd_body = "---------- Forwarded message ----------\n"

        if body_text:
            fwd_body += body_text

        if attachment_names:
            fwd_body += "\n\n[Attachments: " + ", ".join(attachment_names) + "]"

        params = urllib.parse.urlencode(
            {
                "subject": fwd_subject,
                "body": fwd_body,
            }
        )

        return f"mailto:?{params}"

    # ------------------------------------------------------------------
    # Graph API: true server-side forward
    # ------------------------------------------------------------------

    @staticmethod
    def forward_via_graph(
        message_id: str,
        to_email: str,
        comment: str,
        access_token: str,
    ) -> bool:
        """
        Uses Microsoft Graph to forward an email server-side.
        This preserves original attachments automatically.
        """

        if not message_id or not to_email or not access_token:
            return False

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "comment": comment or "",
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email,
                    }
                }
            ],
        }

        url = _mailbox_url(f"messages/{message_id}/forward")

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=20,
            )

            print("GRAPH FORWARD STATUS:", resp.status_code)
            print("GRAPH FORWARD RESPONSE:", resp.text[:1000])

            resp.raise_for_status()
            return True

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Graph forward failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Graph API: true server-side reply
    # ------------------------------------------------------------------

    @staticmethod
    def reply_via_graph(
        message_id: str,
        comment: str,
        access_token: str,
    ) -> bool:
        """
        Uses Microsoft Graph to reply to an email server-side.
        This keeps the reply in the original Outlook thread.
        """

        if not message_id or not access_token:
            return False

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "comment": comment or "",
        }

        url = _mailbox_url(f"messages/{message_id}/reply")

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=20,
            )

            print("GRAPH REPLY STATUS:", resp.status_code)
            print("GRAPH REPLY RESPONSE:", resp.text[:1000])

            resp.raise_for_status()
            return True

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Graph reply failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Attachment download proxy
    # ------------------------------------------------------------------

    @staticmethod
    def get_attachment_bytes(
        message_id: str,
        attachment_id: str,
        access_token: str,
    ) -> Optional[Tuple[bytes, str, str]]:
        """
        Downloads one attachment from Graph and returns:
        (file bytes, filename, content type)
        """

        if not message_id or not attachment_id or not access_token:
            return None

        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        url = _mailbox_url(f"messages/{message_id}/attachments/{attachment_id}")

        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=30,
            )

            print("ATTACHMENT DOWNLOAD STATUS:", resp.status_code)
            print("ATTACHMENT DOWNLOAD RESPONSE:", resp.text[:1000])

            resp.raise_for_status()

            data = resp.json()

            content_bytes = data.get("contentBytes") or ""
            raw_bytes = base64.b64decode(content_bytes)

            filename = data.get("name") or "attachment"
            content_type = data.get("contentType") or "application/octet-stream"

            return raw_bytes, filename, content_type

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Attachment download failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_html(value: str) -> str:
        if not value:
            return ""

        # Drop <style>/<script> blocks (content and all).
        value = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", value, flags=re.IGNORECASE | re.DOTALL)

        # Block-level closers → newline so fields land on their own lines.
        value = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(
            r"</\s*(p|div|tr|li|h[1-6]|table|thead|tbody|ul|ol)\s*>",
            "\n", value, flags=re.IGNORECASE,
        )
        # Table cells → space so "Label" and "value" in adjacent cells don't jam.
        value = re.sub(r"</\s*(td|th)\s*>", " ", value, flags=re.IGNORECASE)

        # Strip remaining tags, then decode entities (&nbsp;, &amp;, …).
        value = re.sub(r"<[^>]+>", "", value)
        value = html.unescape(value)

        # Normalise whitespace.
        value = value.replace("\xa0", " ")          # non-breaking space char
        value = re.sub(r"[ \t]+", " ", value)        # collapse runs of spaces/tabs
        value = re.sub(r" *\n *", "\n", value)       # trim around newlines
        value = re.sub(r"\n{3,}", "\n\n", value)     # collapse blank lines

        return value.strip()

    @staticmethod
    def _format_size(size_bytes) -> str:
        if not size_bytes:
            return ""

        try:
            size = int(size_bytes)
            kb = size / 1024

            if kb < 1024:
                return f"{kb:.1f} KB"

            return f"{kb / 1024:.1f} MB"

        except Exception:
            return ""
        

    @staticmethod
    def reply_with_attachments_via_graph(
        message_id: str,
        comment: str,
        attachments: list,
        access_token: str,
    ) -> bool:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        create_reply_url = _mailbox_url(f"messages/{message_id}/createReply")

        try:
            draft_resp = requests.post(create_reply_url, headers=headers, timeout=20)
            draft_resp.raise_for_status()
            draft = draft_resp.json()
            draft_id = draft.get("id")

            if not draft_id:
                return False

            update_resp = requests.patch(
                _mailbox_url(f"messages/{draft_id}"),
                headers=headers,
                json={"body": {"contentType": "Text", "content": comment or ""}},
                timeout=20,
            )
            update_resp.raise_for_status()

            for attachment in attachments:
                att_resp = requests.post(
                    _mailbox_url(f"messages/{draft_id}/attachments"),
                    headers=headers,
                    json=attachment,
                    timeout=30,
                )
                att_resp.raise_for_status()

            send_resp = requests.post(
                _mailbox_url(f"messages/{draft_id}/send"),
                headers=headers,
                timeout=20,
            )
            send_resp.raise_for_status()

            return True

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Reply with attachments failed: {exc}")
            return False

    @staticmethod
    def forward_with_attachments_via_graph(
    message_id: str,
    to_email: str,
    comment: str,
    attachments: list,
    access_token: str,
    subject: str = "",
    is_html: bool = False,
) -> bool:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        create_forward_url = _mailbox_url(f"messages/{message_id}/createForward")

        try:
            draft_resp = requests.post(create_forward_url, headers=headers, timeout=20)
            draft_resp.raise_for_status()
            draft = draft_resp.json()
            draft_id = draft.get("id")

            if not draft_id:
                return False

            update_payload = {
                "toRecipients": [
                    {"emailAddress": {"address": to_email}}
                ],
                "body": {
                    "contentType": "HTML" if is_html else "Text",
                    "content": comment or "",
                },
            }

            if subject:
                update_payload["subject"] = subject

            update_resp = requests.patch(
                _mailbox_url(f"messages/{draft_id}"),
                headers=headers,
                json=update_payload,
                timeout=20,
            )
            update_resp.raise_for_status()

            for attachment in attachments:
                att_resp = requests.post(
                    _mailbox_url(f"messages/{draft_id}/attachments"),
                    headers=headers,
                    json=attachment,
                    timeout=30,
                )
                att_resp.raise_for_status()

            send_resp = requests.post(
                _mailbox_url(f"messages/{draft_id}/send"),
                headers=headers,
                timeout=20,
            )
            send_resp.raise_for_status()

            return True

        except Exception as exc:
            print(f"[OutlookCaseActivityService] Forward with attachments failed: {exc}")
            return False
