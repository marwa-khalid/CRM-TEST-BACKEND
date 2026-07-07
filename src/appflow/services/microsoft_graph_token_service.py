import os
import time
from pathlib import Path
from threading import Lock
from typing import Optional

import requests
from dotenv import find_dotenv, load_dotenv, set_key

# Resolve the .env once so rotated refresh tokens can be persisted back to it.
_ENV_PATH = find_dotenv() or str(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(_ENV_PATH)


class MicrosoftGraphTokenService:
    _cached_token: Optional[str] = None
    _expires_at: float = 0
    _refresh_token: Optional[str] = None
    _lock = Lock()

    @classmethod
    def get_access_token(cls) -> str:
        with cls._lock:
            if cls._cached_token and time.time() < cls._expires_at:
                return cls._cached_token

            token = cls._legacy_access_token()
            if token:
                return token

            token = cls._acquire_refresh_token()
            if token:
                return token

            token = cls._acquire_client_credentials_token()
            if token:
                return token

            return ""

    @classmethod
    def _legacy_access_token(cls) -> str:
        token = cls._normalize_access_token(os.getenv("OUTLOOK_ACCESS_TOKEN") or "")
        if not token:
            return ""

        return token

    @staticmethod
    def _normalize_access_token(token: str) -> str:
        token = token.strip().strip("\"'")
        if token.lower().startswith("bearer "):
            return token[7:].strip()
        return token

    @staticmethod
    def mailbox_user() -> str:
        tenant_id = MicrosoftGraphTokenService._tenant_id().lower()
        has_refresh_token = bool(
            MicrosoftGraphTokenService._refresh_token
            or os.getenv("OUTLOOK_REFRESH_TOKEN")
            or os.getenv("MS_GRAPH_REFRESH_TOKEN")
        )
        force_mailbox_user = (
            os.getenv("MS_GRAPH_FORCE_MAILBOX_USER", "").strip().lower()
            in {"1", "true", "yes"}
        )

        if tenant_id == "consumers" or (has_refresh_token and not force_mailbox_user):
            return ""

        return (
            os.getenv("MS_GRAPH_MAILBOX")
            or os.getenv("OUTLOOK_MAILBOX")
            or ""
        ).strip()

    @staticmethod
    def _tenant_id() -> str:
        return (
            os.getenv("MS_GRAPH_TENANT_ID")
            or os.getenv("AZURE_TENANT_ID")
            or os.getenv("MICROSOFT_TENANT_ID")
            or ""
        ).strip()

    @staticmethod
    def _client_id() -> str:
        return (
            os.getenv("MS_GRAPH_CLIENT_ID")
            or os.getenv("AZURE_CLIENT_ID")
            or os.getenv("MICROSOFT_CLIENT_ID")
            or ""
        ).strip()

    @staticmethod
    def _client_secret() -> str:
        return (
            os.getenv("MS_GRAPH_CLIENT_SECRET")
            or os.getenv("AZURE_CLIENT_SECRET")
            or os.getenv("MICROSOFT_CLIENT_SECRET")
            or ""
        ).strip()

    @classmethod
    def _token_url(cls) -> str:
        return (
            f"https://login.microsoftonline.com/"
            f"{cls._tenant_id()}/oauth2/v2.0/token"
        )

    @classmethod
    def _cache_result(cls, result: dict) -> str:
        access_token = (result.get("access_token") or "").strip()
        if not access_token:
            return ""

        expires_in = int(result.get("expires_in") or 3600)
        cls._cached_token = access_token
        cls._expires_at = time.time() + max(expires_in - 300, 60)

        refresh_token = (result.get("refresh_token") or "").strip()
        if refresh_token and refresh_token != cls._refresh_token:
            cls._refresh_token = refresh_token
            cls._persist_refresh_token(refresh_token)

        return access_token

    @classmethod
    def _persist_refresh_token(cls, token: str) -> None:
        """Write the rotated refresh token back to .env so it survives restarts.
        Microsoft rotates the refresh token on every use; persisting the latest
        keeps the 90-day rolling window alive indefinitely (no re-consent)."""
        if not token or not _ENV_PATH:
            return
        try:
            set_key(_ENV_PATH, "MS_GRAPH_REFRESH_TOKEN", token, quote_mode="never")
            os.environ["MS_GRAPH_REFRESH_TOKEN"] = token
        except Exception as exc:
            print(f"[MicrosoftGraphTokenService] Could not persist refresh token: {exc}")

    @classmethod
    def _acquire_client_credentials_token(cls) -> str:
        tenant_id = cls._tenant_id()
        client_id = cls._client_id()
        client_secret = cls._client_secret()

        if tenant_id.lower() == "consumers":
            return ""

        if not (tenant_id and client_id and client_secret):
            return ""

        try:
            response = requests.post(
                cls._token_url(),
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
                timeout=20,
            )
            response.raise_for_status()
            return cls._cache_result(response.json())
        except Exception as exc:
            print(f"[MicrosoftGraphTokenService] Client credentials token failed: {exc}")
            return ""

    @classmethod
    def _acquire_refresh_token(cls) -> str:
        tenant_id = cls._tenant_id()
        client_id = cls._client_id()
        refresh_token = (
            cls._refresh_token
            or os.getenv("OUTLOOK_REFRESH_TOKEN")
            or os.getenv("MS_GRAPH_REFRESH_TOKEN")
            or ""
        ).strip()

        if not (tenant_id and client_id and refresh_token):
            return ""

        data = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": os.getenv(
                "MS_GRAPH_DELEGATED_SCOPES",
                "offline_access User.Read Mail.Read Mail.Send",
            ),
        }

        client_secret = cls._client_secret()
        if client_secret:
            data["client_secret"] = client_secret

        try:
            response = requests.post(cls._token_url(), data=data, timeout=20)
            response.raise_for_status()
            return cls._cache_result(response.json())
        except Exception as exc:
            print(f"[MicrosoftGraphTokenService] Refresh token failed: {exc}")
            return ""
