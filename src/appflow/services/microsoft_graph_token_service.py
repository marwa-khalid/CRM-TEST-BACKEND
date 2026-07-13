import os
import time
from pathlib import Path
from threading import Lock
from typing import Dict, Optional, Tuple

import requests
from dotenv import find_dotenv, load_dotenv, set_key

# Resolve the .env once so rotated refresh tokens can be persisted back to it.
_ENV_PATH = find_dotenv() or str(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(_ENV_PATH)


class MicrosoftGraphTokenService:
    _cached_tokens: Dict[str, str] = {}
    _expires_at: Dict[str, float] = {}
    _refresh_tokens: Dict[str, str] = {}
    _refresh_env_keys: Dict[str, str] = {}
    _lock = Lock()

    @classmethod
    def get_access_token(cls, context: str = "default") -> str:
        context = cls._normalize_context(context)
        with cls._lock:
            cached = cls._cached_tokens.get(context)
            if cached and time.time() < cls._expires_at.get(context, 0):
                return cached

            token = cls._legacy_access_token(context)
            if token:
                return token

            token = cls._acquire_refresh_token(context)
            if token:
                return token

            token = cls._acquire_client_credentials_token(context)
            if token:
                return token

            return ""

    @classmethod
    def _legacy_access_token(cls, context: str) -> str:
        token = cls._normalize_access_token(cls._env_first(cls._access_token_env_keys(context)) or "")
        if not token:
            return ""

        return token

    @staticmethod
    def _normalize_context(context: str) -> str:
        value = (context or "default").strip().lower()
        if value in {"case_activity", "case-activity", "outlook", "mail_read", "mail-read"}:
            return "read"
        if value in {"email", "mail_send", "mail-send", "graph_email"}:
            return "send"
        if value in {"read", "send"}:
            return value
        return "default"

    @staticmethod
    def _env_first(keys: Tuple[str, ...]) -> str:
        for key in keys:
            value = (os.getenv(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _env_first_with_key(keys: Tuple[str, ...]) -> Tuple[str, str]:
        for key in keys:
            value = (os.getenv(key) or "").strip()
            if value:
                return value, key
        return "", ""

    @staticmethod
    def _access_token_env_keys(context: str) -> Tuple[str, ...]:
        if context == "read":
            return ("OUTLOOK_READ_ACCESS_TOKEN", "MS_GRAPH_READ_ACCESS_TOKEN", "OUTLOOK_ACCESS_TOKEN")
        if context == "send":
            return ("OUTLOOK_SEND_ACCESS_TOKEN", "MS_GRAPH_SEND_ACCESS_TOKEN")
        return ("OUTLOOK_ACCESS_TOKEN",)

    @staticmethod
    def _refresh_token_env_keys(context: str) -> Tuple[str, ...]:
        if context == "read":
            return (
                "MS_GRAPH_READ_REFRESH_TOKEN",
                "MS_GRAPH_CASE_ACTIVITY_REFRESH_TOKEN",
                "OUTLOOK_READ_REFRESH_TOKEN",
                "OUTLOOK_REFRESH_TOKEN",
                "MS_GRAPH_REFRESH_TOKEN",
            )
        if context == "send":
            return (
                "MS_GRAPH_SEND_REFRESH_TOKEN",
                "MS_GRAPH_EMAIL_REFRESH_TOKEN",
                "OUTLOOK_SEND_REFRESH_TOKEN",
            )
        return ("OUTLOOK_REFRESH_TOKEN", "MS_GRAPH_REFRESH_TOKEN")

    @staticmethod
    def _default_refresh_env_key(context: str) -> str:
        if context == "read":
            return "MS_GRAPH_READ_REFRESH_TOKEN"
        if context == "send":
            return "MS_GRAPH_SEND_REFRESH_TOKEN"
        return "MS_GRAPH_REFRESH_TOKEN"

    @staticmethod
    def _normalize_access_token(token: str) -> str:
        token = token.strip().strip("\"'")
        if token.lower().startswith("bearer "):
            return token[7:].strip()
        return token

    @staticmethod
    def mailbox_user(context: str = "read") -> str:
        context = MicrosoftGraphTokenService._normalize_context(context)
        tenant_id = MicrosoftGraphTokenService._tenant_id(context).lower()
        has_refresh_token = bool(
            MicrosoftGraphTokenService._refresh_tokens.get(context)
            or MicrosoftGraphTokenService._env_first(MicrosoftGraphTokenService._refresh_token_env_keys(context))
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
    def _tenant_id(context: str = "default") -> str:
        context = MicrosoftGraphTokenService._normalize_context(context)
        if context == "read":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_READ_TENANT_ID",
                "MS_GRAPH_CASE_ACTIVITY_TENANT_ID",
                "OUTLOOK_READ_TENANT_ID",
                "MS_GRAPH_TENANT_ID",
                "AZURE_TENANT_ID",
                "MICROSOFT_TENANT_ID",
            ))
        if context == "send":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_SEND_TENANT_ID",
                "MS_GRAPH_EMAIL_TENANT_ID",
                "OUTLOOK_SEND_TENANT_ID",
                "MS_GRAPH_TENANT_ID",
                "AZURE_TENANT_ID",
                "MICROSOFT_TENANT_ID",
            ))
        return MicrosoftGraphTokenService._env_first((
            "MS_GRAPH_TENANT_ID",
            "AZURE_TENANT_ID",
            "MICROSOFT_TENANT_ID",
        ))

    @staticmethod
    def _client_id(context: str = "default") -> str:
        context = MicrosoftGraphTokenService._normalize_context(context)
        if context == "read":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_READ_CLIENT_ID",
                "MS_GRAPH_CASE_ACTIVITY_CLIENT_ID",
                "OUTLOOK_READ_CLIENT_ID",
                "MS_GRAPH_CLIENT_ID",
                "AZURE_CLIENT_ID",
                "MICROSOFT_CLIENT_ID",
            ))
        if context == "send":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_SEND_CLIENT_ID",
                "MS_GRAPH_EMAIL_CLIENT_ID",
                "OUTLOOK_SEND_CLIENT_ID",
                "MS_GRAPH_CLIENT_ID",
                "AZURE_CLIENT_ID",
                "MICROSOFT_CLIENT_ID",
            ))
        return MicrosoftGraphTokenService._env_first((
            "MS_GRAPH_CLIENT_ID",
            "AZURE_CLIENT_ID",
            "MICROSOFT_CLIENT_ID",
        ))

    @staticmethod
    def _client_secret(context: str = "default") -> str:
        context = MicrosoftGraphTokenService._normalize_context(context)
        if context == "read":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_READ_CLIENT_SECRET",
                "MS_GRAPH_CASE_ACTIVITY_CLIENT_SECRET",
                "OUTLOOK_READ_CLIENT_SECRET",
                "MS_GRAPH_CLIENT_SECRET",
                "AZURE_CLIENT_SECRET",
                "MICROSOFT_CLIENT_SECRET",
            ))
        if context == "send":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_SEND_CLIENT_SECRET",
                "MS_GRAPH_EMAIL_CLIENT_SECRET",
                "OUTLOOK_SEND_CLIENT_SECRET",
                "MS_GRAPH_CLIENT_SECRET",
                "AZURE_CLIENT_SECRET",
                "MICROSOFT_CLIENT_SECRET",
            ))
        return MicrosoftGraphTokenService._env_first((
            "MS_GRAPH_CLIENT_SECRET",
            "AZURE_CLIENT_SECRET",
            "MICROSOFT_CLIENT_SECRET",
        ))

    @staticmethod
    def _scopes(context: str = "default") -> str:
        context = MicrosoftGraphTokenService._normalize_context(context)
        if context == "read":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_READ_DELEGATED_SCOPES",
                "MS_GRAPH_DELEGATED_SCOPES",
            )) or "offline_access User.Read Mail.Read"
        if context == "send":
            return MicrosoftGraphTokenService._env_first((
                "MS_GRAPH_SEND_DELEGATED_SCOPES",
                "MS_GRAPH_EMAIL_DELEGATED_SCOPES",
                "MS_GRAPH_DELEGATED_SCOPES",
            )) or "offline_access User.Read Mail.Send"
        return os.getenv(
            "MS_GRAPH_DELEGATED_SCOPES",
            "offline_access User.Read Mail.Read Mail.Send",
        )

    @classmethod
    def _token_url(cls, context: str = "default") -> str:
        return (
            f"https://login.microsoftonline.com/"
            f"{cls._tenant_id(context)}/oauth2/v2.0/token"
        )

    @classmethod
    def _cache_result(cls, result: dict, context: str, refresh_env_key: str = "") -> str:
        access_token = (result.get("access_token") or "").strip()
        if not access_token:
            return ""

        expires_in = int(result.get("expires_in") or 3600)
        cls._cached_tokens[context] = access_token
        cls._expires_at[context] = time.time() + max(expires_in - 300, 60)

        refresh_token = (result.get("refresh_token") or "").strip()
        if refresh_token and refresh_token != cls._refresh_tokens.get(context):
            cls._refresh_tokens[context] = refresh_token
            key = refresh_env_key or cls._refresh_env_keys.get(context) or cls._default_refresh_env_key(context)
            cls._refresh_env_keys[context] = key
            cls._persist_refresh_token(refresh_token, key)

        return access_token

    @classmethod
    def _persist_refresh_token(cls, token: str, env_key: str) -> None:
        """Write the rotated refresh token back to .env so it survives restarts.
        Microsoft rotates the refresh token on every use; persisting the latest
        keeps the 90-day rolling window alive indefinitely (no re-consent)."""
        if not token or not env_key or not _ENV_PATH:
            return
        try:
            set_key(_ENV_PATH, env_key, token, quote_mode="never")
            os.environ[env_key] = token
        except Exception as exc:
            print(f"[MicrosoftGraphTokenService] Could not persist refresh token: {exc}")

    @classmethod
    def _acquire_client_credentials_token(cls, context: str) -> str:
        tenant_id = cls._tenant_id(context)
        client_id = cls._client_id(context)
        client_secret = cls._client_secret(context)

        if tenant_id.lower() == "consumers":
            return ""

        if not (tenant_id and client_id and client_secret):
            return ""

        try:
            response = requests.post(
                cls._token_url(context),
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
                timeout=20,
            )
            response.raise_for_status()
            return cls._cache_result(response.json(), context)
        except Exception as exc:
            print(f"[MicrosoftGraphTokenService] Client credentials token failed: {exc}")
            return ""

    @classmethod
    def _acquire_refresh_token(cls, context: str) -> str:
        tenant_id = cls._tenant_id(context)
        client_id = cls._client_id(context)
        refresh_token = cls._refresh_tokens.get(context) or ""
        refresh_env_key = cls._refresh_env_keys.get(context) or ""
        if not refresh_token:
            refresh_token, refresh_env_key = cls._env_first_with_key(cls._refresh_token_env_keys(context))
            if refresh_token:
                cls._refresh_tokens[context] = refresh_token
                cls._refresh_env_keys[context] = refresh_env_key

        if not (tenant_id and client_id and refresh_token):
            missing = []
            if not tenant_id:
                missing.append("tenant_id")
            if not client_id:
                missing.append("client_id")
            if not refresh_token:
                missing.append("refresh_token")
            print(
                "[MicrosoftGraphTokenService] Refresh token skipped "
                f"for context={context}: missing {', '.join(missing)}"
            )
            return ""

        data = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": cls._scopes(context),
        }

        client_secret = cls._client_secret(context)
        if client_secret:
            data["client_secret"] = client_secret

        try:
            response = requests.post(cls._token_url(context), data=data, timeout=20)
            response.raise_for_status()
            return cls._cache_result(response.json(), context, refresh_env_key)
        except Exception as exc:
            client_hint = f"{client_id[:8]}..." if client_id else "missing"
            env_key = refresh_env_key or cls._default_refresh_env_key(context)
            response = getattr(exc, "response", None)
            body = ""
            if response is not None:
                body = f" body={response.text[:500]}"
            print(
                "[MicrosoftGraphTokenService] Refresh token failed "
                f"for context={context}, env={env_key}, client_id={client_hint}: {exc}{body}"
            )
            return ""
