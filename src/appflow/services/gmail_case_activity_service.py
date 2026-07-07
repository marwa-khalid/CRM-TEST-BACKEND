import os
import base64
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from appflow.models.case_activity import CaseActivityAttachmentOut, CaseActivityItemOut


class GmailCaseActivityService:
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self):
        self.client_id = os.getenv("GMAIL_CLIENT_ID")
        self.client_secret = os.getenv("GMAIL_CLIENT_SECRET")
        self.refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise ValueError("Missing Gmail OAuth env vars.")

        creds = Credentials(
            None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.SCOPES,
        )
        creds.refresh(Request())
        self.service = build("gmail", "v1", credentials=creds)

    def search_case_emails(self, case_reference: str) -> List[CaseActivityItemOut]:
        query = f'"{case_reference}"'
        result = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=20)
            .execute()
        )

        messages = result.get("messages", [])
        items: List[CaseActivityItemOut] = []

        for msg in messages:
            full = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )

            payload = full.get("payload", {})
            headers = payload.get("headers", [])

            subject = self._header(headers, "Subject")
            from_raw = self._header(headers, "From")
            date_raw = self._header(headers, "Date")
            sender_name, sender_email = self._parse_from(from_raw)
            received_at = self._parse_date(date_raw)

            body_text = self._extract_body(payload)
            snippet = full.get("snippet", "")

            attachments = self._extract_attachments(payload)

            items.append(
                CaseActivityItemOut(
                    id=f"email-{full['id']}",
                    type="Email",
                    title="Email from Client",
                    timestamp=received_at or datetime.utcnow(),
                    badge_label="Email",
                    summary=subject or "Email",
                    subject=subject,
                    sender_name=sender_name,
                    sender_email=sender_email,
                    received_at=received_at,
                    body_preview=snippet,
                    body_text=body_text or snippet,
                    attachments=attachments,
                    raw={
                        "gmail_message_id": full["id"],
                        "thread_id": full.get("threadId"),
                    },
                )
            )

        return items

    def _header(self, headers: list, name: str) -> str:
        for h in headers:
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    def _parse_from(self, from_value: str):
        if "<" in from_value and ">" in from_value:
            name = from_value.split("<")[0].strip().strip('"')
            email = from_value.split("<")[1].split(">")[0].strip()
            return name or email, email
        return from_value, from_value

    def _parse_date(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return parsedate_to_datetime(value)
        except Exception:
            return None

    def _extract_body(self, payload: dict) -> str:
        body = payload.get("body", {})
        data = body.get("data")
        if data:
            return self._decode_base64(data)

        for part in payload.get("parts", []) or []:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain" and part.get("body", {}).get("data"):
                return self._decode_base64(part["body"]["data"])

        for part in payload.get("parts", []) or []:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/html" and part.get("body", {}).get("data"):
                return self._decode_base64(part["body"]["data"])

        return ""

    def _extract_attachments(self, payload: dict) -> List[CaseActivityAttachmentOut]:
        results: List[CaseActivityAttachmentOut] = []

        def walk(parts: list):
            for part in parts or []:
                filename = part.get("filename")
                body = part.get("body", {})
                mime_type = part.get("mimeType")

                if filename:
                    results.append(
                        CaseActivityAttachmentOut(
                            file_name=filename,
                            file_url=None,
                            content_type=mime_type,
                            size_bytes=body.get("size"),
                        )
                    )

                if part.get("parts"):
                    walk(part.get("parts", []))

        walk(payload.get("parts", []))
        return results

    def _decode_base64(self, data: str) -> str:
        try:
            decoded = base64.urlsafe_b64decode(data.encode("UTF-8"))
            return decoded.decode("utf-8", errors="ignore")
        except Exception:
            return ""