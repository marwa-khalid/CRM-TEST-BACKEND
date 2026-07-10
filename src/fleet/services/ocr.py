"""Self-contained OCR for the Fleet module.

Deliberately independent of the Claims OCR services (vehicle_upload_service etc.)
so the whole Fleet slice can be extracted to its own project later without
dragging Claims code along. Free by default (local Tesseract); optionally uses
Google Vision when GOOGLE_VISION_API_KEY is set — a plain API key, so it works
even when the org blocks service-account keys.
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from typing import Dict, List

import pytesseract
from PIL import Image

try:  # PyMuPDF, only needed for PDF uploads
    import fitz
except Exception:  # pragma: no cover - optional
    fitz = None


# --------------------------------------------------------------------------- #
# OCR engine (Vision API key first if configured, else free local Tesseract)
# --------------------------------------------------------------------------- #
def _vision_api_key_ocr(image_bytes: bytes) -> str | None:
    api_key = os.getenv("GOOGLE_VISION_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        body = json.dumps(
            {
                "requests": [
                    {
                        "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                    }
                ]
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = (data.get("responses") or [{}])[0]
        if (result.get("error") or {}).get("message"):
            raise RuntimeError(result["error"]["message"])
        full = (result.get("fullTextAnnotation") or {}).get("text")
        if full:
            return full
        annotations = result.get("textAnnotations") or []
        return annotations[0].get("description", "") if annotations else ""
    except Exception as exc:  # pylint: disable=broad-exception-caught
        detail = str(exc)
        if isinstance(exc, urllib.error.HTTPError):
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        print(f"Fleet Vision API-key OCR failed: {detail}")
        return None


def _image_bytes_to_text(image_bytes: bytes) -> str:
    api_text = _vision_api_key_ocr(image_bytes)
    if api_text and api_text.strip():
        return api_text
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return pytesseract.image_to_string(img)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Fleet local OCR failed: {exc}")
        return ""


def file_to_text(file_bytes: bytes, filename: str = "") -> str:
    """OCR an uploaded image or PDF (all pages) to plain text."""
    if filename.lower().endswith(".pdf") and fitz is not None:
        parts: List[str] = []
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                parts.append(_image_bytes_to_text(pix.tobytes("png")))
            doc.close()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Fleet PDF OCR failed: {exc}")
        return "\n".join(parts)
    return _image_bytes_to_text(file_bytes)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b")
_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")


def _find_postcode(text: str) -> str:
    m = _POSTCODE.search(text.upper())
    return f"{m.group(1)} {m.group(2)}" if m else ""


def _all_dates(text: str) -> List[date]:
    out: List[date] = []
    for d, mo, y in _DATE.findall(text):
        year = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            out.append(date(year, int(mo), int(d)))
        except ValueError:
            pass
    return out


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
def parse_driving_licence(text: str) -> Dict[str, str]:
    """Best-effort extraction of driver fields from a UK photocard licence.

    Reliable: licence number, date of birth, postcode. Name/address are
    best-effort (the numbered field labels OCR inconsistently) and are meant as
    an editable auto-fill, not a guarantee.
    """
    result = {
        "name": "",
        "address": "",
        "postcode": "",
        "drivingLicenceNumber": "",
        "dateOfBirth": "",
        "licenceStart": "",
        "licenceEnd": "",
    }
    if not text or not text.strip():
        return result

    upper = text.upper()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Field 5 — DVLA driver number: 4-5 letters, 6 digits, 3-7 alphanumerics.
    m = re.search(r"\b([A-Z9]{4,5}\d{6}[A-Z0-9]{3,7})\b", upper)
    if m:
        result["drivingLicenceNumber"] = m.group(1)

    # Dates: earliest = DOB (field 3); latest = expiry (4b); the middle = issue (4a).
    dates = sorted(set(_all_dates(text)))
    if dates:
        result["dateOfBirth"] = dates[0].isoformat()
        if len(dates) >= 2:
            result["licenceEnd"] = dates[-1].strftime("%d-%m-%Y")
        if len(dates) >= 3:
            result["licenceStart"] = dates[1].strftime("%d-%m-%Y")

    result["postcode"] = _find_postcode(text)

    # Fields 1 (surname) + 2 (first names), read from the numbered markers.
    surname = firstnames = ""
    for line in lines:
        s = re.match(r"^1[.\s]+([A-Z][A-Z '\-]{1,})$", line.upper())
        if s and not surname:
            surname = s.group(1).strip()
        f = re.match(r"^2[.\s]+([A-Z][A-Z '\-]{1,})$", line.upper())
        if f and not firstnames:
            firstnames = f.group(1).strip()
    name = " ".join(p for p in [firstnames.title(), surname.title()] if p).strip()
    result["name"] = name

    # Field 8 — address: the postcode line + up to two short lines above it.
    if result["postcode"]:
        compact_pc = result["postcode"].replace(" ", "")
        for i, line in enumerate(lines):
            if compact_pc in line.upper().replace(" ", ""):
                parts = []
                for j in range(max(0, i - 2), i + 1):
                    seg = re.sub(r"^8[.\s]+", "", lines[j])
                    if _DATE.search(seg) or re.search(r"[A-Z9]{4,5}\d{6}", seg.upper()):
                        continue
                    parts.append(seg)
                addr = re.sub(re.escape(result["postcode"]), "", " ".join(parts), flags=re.IGNORECASE)
                result["address"] = re.sub(r"\s{2,}", " ", addr).strip(" ,").title()
                break
    return result


def parse_proof_of_address(text: str) -> Dict[str, str]:
    """Extract the address block + postcode from a proof-of-address (utility bill)."""
    result = {"address": "", "postcode": ""}
    if not text or not text.strip():
        return result

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    postcode = ""
    pc_index = -1
    for i, line in enumerate(lines):
        m = _POSTCODE.search(line.upper())
        if m:
            postcode = f"{m.group(1)} {m.group(2)}"
            pc_index = i
            break
    result["postcode"] = postcode

    if pc_index >= 0:
        block: List[str] = []
        for j in range(pc_index, max(-1, pc_index - 4), -1):
            seg = lines[j]
            if _DATE.search(seg):  # skip a bill/issue date sitting in the block
                continue
            block.insert(0, seg)
        # The address starts at the first house-number line — drop any name line
        # above it so it lines up with the licence address for comparison.
        start = 0
        for k, seg in enumerate(block):
            if re.search(r"\d", seg) and not _POSTCODE.search(seg.upper()):
                start = k
                break
        addr = re.sub(re.escape(postcode), "", " ".join(block[start:]), flags=re.IGNORECASE)
        result["address"] = re.sub(r"\s{2,}", " ", addr).strip(" ,").title()
    return result
