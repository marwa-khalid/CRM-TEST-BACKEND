"""LLM-based field extraction from V5C OCR text (Claude / Anthropic SDK).

Google Vision reads the V5C reliably, but the regex parsers that turn that text
into structured fields are brittle across V5C layouts — which is why vehicle /
owner extraction often came back empty while engineer OCR worked. Claude reads
the raw OCR text and returns the structured fields robustly.

This module is best-effort and self-contained: if ANTHROPIC_API_KEY is unset, or
the SDK isn't installed, or the call fails, every function returns None so the
caller falls back to its existing regex parser. Nothing here can break the OCR
import.
"""
import json
import os
import re
from typing import Any, Dict, Optional

# Per the Claude API guidance, default to Opus 4.8. Overridable without a code
# change (e.g. set LLM_EXTRACTION_MODEL=claude-haiku-4-5 for lower latency/cost).
_MODEL = os.getenv("LLM_EXTRACTION_MODEL", "claude-opus-4-8").strip() or "claude-opus-4-8"

_client = None
_client_disabled = False


def _get_client():
    """Lazily construct the Anthropic client. Returns None when unavailable."""
    global _client, _client_disabled
    if _client is not None or _client_disabled:
        return _client
    # Opt-in. By default V5C extraction stays on the plain Vision + regex path
    # (same as the engineer screen). Set USE_LLM_EXTRACTION=true (plus
    # ANTHROPIC_API_KEY) to route vehicle/owner extraction through Claude.
    if os.getenv("USE_LLM_EXTRACTION", "").strip().lower() not in ("1", "true", "yes", "on"):
        _client_disabled = True
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        _client_disabled = True
        return None
    try:
        import anthropic  # imported lazily so a missing dep never breaks OCR
        _client = anthropic.Anthropic(api_key=api_key)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"LLM extractor: Anthropic client unavailable ({exc}); using regex fallback")
        _client_disabled = True
        _client = None
    return _client


def _loads_json(text: str) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:  # pylint: disable=broad-exception-caught
        # Be forgiving if the model wrapped the object in prose/code fences.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except Exception:  # pylint: disable=broad-exception-caught
            return None
    return data if isinstance(data, dict) else None


_SYSTEM = (
    "You are a precise data-extraction engine for UK V5C vehicle registration "
    "documents. Respond with ONLY a single JSON object using exactly the requested "
    "keys — no prose, no explanation, no markdown, no code fences. Use an empty "
    "string for any field you cannot find. Never guess or invent values."
)


def _call_claude(prompt: str) -> Optional[Dict[str, Any]]:
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"LLM extractor: Claude request failed ({exc}); using regex fallback")
        return None
    text = "".join(
        getattr(b, "text", "") for b in getattr(resp, "content", []) or []
        if getattr(b, "type", None) == "text"
    )
    return _loads_json(text)


# ---- Vehicle details ------------------------------------------------------
# Frontend dropdown values (must match): Petrol=1, Diesel=2, Electric=3, Hybrid=4;
# Automatic=1, Manual=2.
_FUEL_TO_ID = {"petrol": 1, "diesel": 2, "electric": 3, "hybrid": 4}
_TRANSMISSION_TO_ID = {"automatic": 1, "manual": 2}

_VEHICLE_PROMPT = """Extract the vehicle details from this UK V5C OCR text.

Return a JSON object with exactly these keys:
- "make": manufacturer (V5C field D.1), e.g. "TOYOTA".
- "model": model / type (V5C field D.3), e.g. "AURIS ICON TSS HYBRD VVT-I CVT".
- "body_type": body type, e.g. "ESTATE".
- "registration": number plate, uppercase with no spaces, e.g. "MX17VHA".
- "color": colour (V5C field D.5), e.g. "WHITE".
- "engine_size": cylinder capacity in cc including units if present, e.g. "1798 CC".
- "fuel_type": one of "Petrol", "Diesel", "Electric", "Hybrid", or "".
- "transmission": one of "Automatic", "Manual", or "".
- "number_of_seat": number of seats as a string, or "".
- "vehicle_category": vehicle category, or "".

OCR TEXT:
---
{text}
---"""


def extract_vehicle_fields_llm(ocr_text: str) -> Optional[Dict[str, Any]]:
    """Return the vehicle-detail dict (same shape as the regex parser) or None."""
    if not ocr_text or not ocr_text.strip():
        return None
    data = _call_claude(_VEHICLE_PROMPT.format(text=ocr_text[:8000]))
    if not data:
        return None
    fuel = str(data.get("fuel_type", "")).strip().lower()
    trans = str(data.get("transmission", "")).strip().lower()
    result = {
        "make": str(data.get("make", "") or "").strip(),
        "model": str(data.get("model", "") or "").strip(),
        "body_type": str(data.get("body_type", "") or "").strip(),
        "registration": str(data.get("registration", "") or "").strip().replace(" ", "").upper(),
        "color": str(data.get("color", "") or "").strip(),
        "engine_size": str(data.get("engine_size", "") or "").strip(),
        "fuel_type_id": _FUEL_TO_ID.get(fuel),
        "transmission_id": _TRANSMISSION_TO_ID.get(trans),
        "number_of_seat": str(data.get("number_of_seat", "") or "").strip(),
        "vehicle_category": str(data.get("vehicle_category", "") or "").strip(),
    }
    # Only trust the LLM result if it actually found something identifying.
    if result["make"] or result["registration"] or result["model"]:
        return result
    return None


# ---- Owner / registered keeper -------------------------------------------
_OWNER_PROMPT = """Extract the registered keeper (owner) details from this UK V5C OCR text.

Return a JSON object with exactly these keys:
- "first_name": the keeper's first name. For a company keeper, put the leading word(s) here.
- "surname": the keeper's surname. For a company keeper, put the remaining words here (e.g. "Investments Ltd").
- "address": the full keeper address on one line, WITHOUT the postcode.
- "postcode": the UK postcode, e.g. "B16 8RP".
- "email": usually not present on a V5C — use "".
- "home_tel": usually not present — use "".
- "mobile_tel": usually not present — use "".
- "payment_benificiary": usually not present — use "".

OCR TEXT:
---
{text}
---"""


def extract_owner_fields_llm(ocr_text: str) -> Optional[Dict[str, Any]]:
    """Return the owner dict (same shape as the regex parser) or None."""
    if not ocr_text or not ocr_text.strip():
        return None
    data = _call_claude(_OWNER_PROMPT.format(text=ocr_text[:8000]))
    if not data:
        return None
    result = {
        "first_name": str(data.get("first_name", "") or "").strip(),
        "surname": str(data.get("surname", "") or "").strip(),
        "address": str(data.get("address", "") or "").strip(),
        "postcode": str(data.get("postcode", "") or "").strip().upper(),
        "email": str(data.get("email", "") or "").strip(),
        "home_tel": str(data.get("home_tel", "") or "").strip(),
        "mobile_tel": str(data.get("mobile_tel", "") or "").strip(),
        "payment_benificiary": str(data.get("payment_benificiary", "") or "").strip(),
    }
    if result["first_name"] or result["surname"] or result["address"]:
        return result
    return None
