"""Fleet SMS delivery.

Provider is selected by env so Fleet stays deployable without hard-coding a
vendor. Supported values:

- SMS_PROVIDER=twilio
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
- SMS_PROVIDER=aws_sns
  AWS_* credentials/region already used by the app, optional AWS_SNS_SMS_SENDER_ID
"""
import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

ON_HIRE_SMS_BODY = (
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


def _send_twilio(to_number: str, body: str) -> dict:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    if not account_sid or not auth_token or not from_number:
        return {"sent": False, "provider": "twilio", "reason": "Twilio env vars are missing"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    response = requests.post(
        url,
        data={"To": to_number, "From": from_number, "Body": body},
        auth=(account_sid, auth_token),
        timeout=20,
    )
    if response.status_code >= 400:
        logger.warning("Twilio SMS failed: %s %s", response.status_code, response.text[:500])
        return {"sent": False, "provider": "twilio", "status_code": response.status_code}

    payload = response.json() if response.content else {}
    return {"sent": True, "provider": "twilio", "sid": payload.get("sid")}


def _send_aws_sns(to_number: str, body: str) -> dict:
    try:
        import boto3
    except ImportError:
        return {"sent": False, "provider": "aws_sns", "reason": "boto3 is not installed"}

    client = boto3.client("sns", region_name=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or "eu-west-1")
    attributes = {
        "AWS.SNS.SMS.SMSType": {
            "DataType": "String",
            "StringValue": os.getenv("AWS_SNS_SMS_TYPE", "Transactional"),
        }
    }
    sender_id = os.getenv("AWS_SNS_SMS_SENDER_ID", "").strip()
    if sender_id:
        attributes["AWS.SNS.SMS.SenderID"] = {"DataType": "String", "StringValue": sender_id[:11]}

    response = client.publish(PhoneNumber=to_number, Message=body, MessageAttributes=attributes)
    return {"sent": True, "provider": "aws_sns", "message_id": response.get("MessageId")}


def send_sms(to_number: Optional[str], body: str) -> dict:
    """Best-effort SMS. Never raises to the caller."""
    normalized = normalize_uk_mobile(to_number)
    if not normalized:
        return {"sent": False, "reason": "Missing or invalid UK mobile number"}

    provider = (os.getenv("SMS_PROVIDER") or "").strip().lower()
    if not provider:
        return {"sent": False, "reason": "SMS_PROVIDER is not configured"}

    try:
        if provider == "twilio":
            return _send_twilio(normalized, body)
        if provider in {"aws", "aws_sns", "sns"}:
            return _send_aws_sns(normalized, body)
        return {"sent": False, "provider": provider, "reason": "Unsupported SMS provider"}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Fleet SMS send failed via %s: %s", provider, exc)
        return {"sent": False, "provider": provider, "reason": str(exc)}


def send_on_hire_sms(driver_mobile: Optional[str]) -> dict:
    return send_sms(driver_mobile, ON_HIRE_SMS_BODY)
