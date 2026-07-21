"""Fleet WhatsApp delivery (replaces the old SMS sending).

Provider is selected by env so Fleet stays deployable without hard-coding a
vendor.

Supported values:

- WHATSAPP_PROVIDER=vonage (default — Vonage Messages API)
  VONAGE_WHATSAPP_FROM (or VONAGE_FROM) — the WhatsApp sender, which must be a
  NUMBER, not an alphanumeric sender id; WhatsApp does not allow those.
  Plus either VONAGE_API_KEY + VONAGE_API_SECRET (Basic auth — required by the
  sandbox) or VONAGE_APPLICATION_ID + VONAGE_PRIVATE_KEY (JWT auth, production).
  Set VONAGE_SANDBOX=true to post to the Messages API sandbox instead of live.

- WHATSAPP_PROVIDER=meta   (WhatsApp Cloud API, direct from Meta)
  WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, optional WHATSAPP_API_VERSION

  Outside the 24-hour window WhatsApp only accepts pre-approved TEMPLATES, so
  each business-initiated message needs its approved template name in env:
      WHATSAPP_TEMPLATE_PAYMENT_REMINDER
      WHATSAPP_TEMPLATE_PRICE_RISE
      WHATSAPP_TEMPLATE_ON_HIRE
      WHATSAPP_TEMPLATE_LANG   (default en_GB)
  With a template configured the approved wording is what sends — any text typed
  in the modal is ignored, because WhatsApp does not allow it to be changed.
  Leave a template unset and that message falls back to free-form text, which is
  what the Vonage sandbox and the 24-hour window allow.

NOTE: outside the 24-hour customer-service window WhatsApp only allows
pre-approved *template* messages. Free-form text (what we send here) works when
the customer has messaged you recently or joined the Vonage sandbox; otherwise
the provider returns an error, which surfaces to the caller.
"""
import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

ON_HIRE_WHATSAPP_BODY = (
    "Thank you for booking your hire vehicle from Skyline Car Hire UK Ltd.\n"
    "We would like to remind you that when using the vehicle, the dash camera must be removed and hidden away for security reasons.\n"
    "We have emailed you with some useful telephone numbers which you may need during the hire period, so please save these numbers to your mobile phone.\n"
    "Please note that in the event of a road traffic accident you must call 0800 410 1999."
)


def normalize_uk_mobile(value: Optional[str]) -> str:
    """Return a UK mobile as +447..., or empty if it is not a UK mobile."""
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    if digits.startswith("0044"):
        digits = digits[4:]
    elif digits.startswith("44"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"7\d{9}", digits):
        return ""
    return f"+44{digits}"


# Message kind -> the env var holding its approved template name.
TEMPLATE_ENV = {
    "reminder": "WHATSAPP_TEMPLATE_PAYMENT_REMINDER",
    "price_rise": "WHATSAPP_TEMPLATE_PRICE_RISE",
    "on_hire": "WHATSAPP_TEMPLATE_ON_HIRE",
}


def template_for(kind: Optional[str]) -> str:
    """Approved template name for this message kind, or "" for free-form text."""
    env_name = TEMPLATE_ENV.get((kind or "").strip().lower())
    return os.getenv(env_name, "").strip() if env_name else ""


def _send_meta(to_number: str, body: str, template: str = "", params: Optional[list] = None) -> dict:
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    version = os.getenv("WHATSAPP_API_VERSION", "v21.0").strip() or "v21.0"
    if not token or not phone_number_id:
        return {
            "sent": False,
            "provider": "meta",
            "reason": "WhatsApp Cloud API env vars are missing (WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID)",
        }

    if template:
        language = os.getenv("WHATSAPP_TEMPLATE_LANG", "en_GB").strip() or "en_GB"
        components = []
        if params:
            components.append({
                "type": "body",
                # Placeholders are positional: {{1}}, {{2}}, ... in template order.
                "parameters": [{"type": "text", "text": str(p)} for p in params],
            })
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number.lstrip("+"),
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": language},
                **({"components": components} if components else {}),
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }

    response = requests.post(
        f"https://graph.facebook.com/{version}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        logger.warning("Meta WhatsApp failed: %s %s", response.status_code, response.text[:500])
        detail = ""
        try:
            detail = ((response.json() or {}).get("error") or {}).get("message", "")
        except Exception:  # pylint: disable=broad-exception-caught
            detail = ""
        return {
            "sent": False,
            "provider": "meta",
            "status_code": response.status_code,
            "reason": detail or "WhatsApp Cloud API send failed",
        }

    payload = response.json() if response.content else {}
    messages = payload.get("messages") or []
    message_id = (messages[0] or {}).get("id") if messages else None
    return {"sent": True, "provider": "meta", "message_id": message_id, "to": to_number}


def _vonage_jwt() -> str:
    """Sign a short-lived Vonage JWT (RS256) from the app id + private key."""
    import time
    import uuid

    import jwt  # PyJWT

    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    private_key = os.getenv("VONAGE_PRIVATE_KEY", "").strip()
    # Railway env vars keep newlines as literal "\n" — restore them for the PEM.
    private_key = private_key.replace("\\n", "\n")
    now = int(time.time())
    return jwt.encode(
        {
            "application_id": application_id,
            "iat": now,
            "exp": now + 300,
            "jti": str(uuid.uuid4()),
        },
        private_key,
        algorithm="RS256",
    )


def _send_vonage(to_number: str, body: str) -> dict:
    # VONAGE_FROM is the old SMS sender; fall back to it, but WhatsApp needs a
    # number, so an alphanumeric sender id ("Skyline") is rejected up front.
    from_number = (
        os.getenv("VONAGE_WHATSAPP_FROM", "").strip() or os.getenv("VONAGE_FROM", "").strip()
    ).lstrip("+")
    api_key = os.getenv("VONAGE_API_KEY", "").strip()
    api_secret = os.getenv("VONAGE_API_SECRET", "").strip()
    application_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    sandbox = (os.getenv("VONAGE_SANDBOX") or "").strip().lower() in {"1", "true", "yes"}

    if not from_number:
        return {"sent": False, "provider": "vonage", "reason": "VONAGE_WHATSAPP_FROM is missing"}
    if not from_number.isdigit():
        return {
            "sent": False,
            "provider": "vonage",
            "reason": (
                f"VONAGE_WHATSAPP_FROM must be a phone number, not an alphanumeric "
                f"sender id ('{from_number}'). WhatsApp senders are always numbers."
            ),
        }

    # The sandbox only accepts Basic auth, so prefer it there even if an
    # application id / private key happen to be set for production.
    if sandbox and api_key and api_secret:
        headers = {}
        auth = (api_key, api_secret)
    # JWT is the production auth; Basic also works on live for most accounts.
    elif application_id and os.getenv("VONAGE_PRIVATE_KEY", "").strip():
        headers = {"Authorization": f"Bearer {_vonage_jwt()}"}
        auth = None
    elif api_key and api_secret:
        headers = {}
        auth = (api_key, api_secret)
    else:
        return {
            "sent": False,
            "provider": "vonage",
            "reason": "Vonage auth env vars are missing (VONAGE_API_KEY / VONAGE_API_SECRET, or VONAGE_APPLICATION_ID / VONAGE_PRIVATE_KEY)",
        }

    host = "messages-sandbox.nexmo.com" if sandbox else "api.nexmo.com"
    response = requests.post(
        f"https://{host}/v1/messages",
        headers=headers,
        auth=auth,
        json={
            "channel": "whatsapp",
            "message_type": "text",
            "to": to_number.lstrip("+"),  # Vonage wants E.164 without the "+"
            "from": from_number,
            "text": body,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        logger.warning("Vonage WhatsApp failed: %s %s", response.status_code, response.text[:500])
        detail = ""
        try:
            payload = response.json() or {}
            detail = payload.get("detail") or payload.get("title") or ""
        except Exception:  # pylint: disable=broad-exception-caught
            detail = ""
        return {
            "sent": False,
            "provider": "vonage",
            "status_code": response.status_code,
            "reason": detail or "Vonage WhatsApp send failed",
        }

    payload = response.json() if response.content else {}
    return {"sent": True, "provider": "vonage", "message_id": payload.get("message_uuid"), "to": to_number}


def send_whatsapp(
    to_number: Optional[str],
    body: str,
    kind: Optional[str] = None,
    params: Optional[list] = None,
) -> dict:
    """Best-effort WhatsApp message. Never raises to the caller.

    `kind` selects an approved template when one is configured; otherwise the
    free-form `body` is sent.
    """
    normalized = normalize_uk_mobile(to_number)
    if not normalized:
        return {"sent": False, "reason": "Missing or invalid UK mobile number"}

    provider = (os.getenv("WHATSAPP_PROVIDER") or "vonage").strip().lower()

    try:
        if provider in {"vonage", "nexmo"}:
            return _send_vonage(normalized, body)
        if provider in {"meta", "cloud", "whatsapp_cloud"}:
            return _send_meta(normalized, body, template_for(kind), params)
        return {"sent": False, "provider": provider, "reason": "Unsupported WhatsApp provider"}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Fleet WhatsApp send failed via %s: %s", provider, exc)
        return {"sent": False, "provider": provider, "reason": str(exc)}


def send_on_hire_whatsapp(driver_mobile: Optional[str]) -> dict:
    return send_whatsapp(driver_mobile, ON_HIRE_WHATSAPP_BODY, kind="on_hire")
