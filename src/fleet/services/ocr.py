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
from PIL import Image, ImageOps

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


# Count of licence field markers (1. 2. 3. 4a. 5. 8. 9.) — a proxy for how cleanly
# OCR captured the card structure; used to pick the best preprocessing variant.
_MARKER_LINE = re.compile(r"(?m)^\s*\d[a-dA-D]?\s*[.)\]:]")


def _preprocess_variants(image_bytes: bytes) -> List["Image.Image"]:
    """A grayscale+autocontrast pass and a binarised pass. Dark ink on a busy pink
    guilloche background (typical UK licence) reads far better once thresholded."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    g = ImageOps.autocontrast(ImageOps.grayscale(img))
    w, h = g.size
    if max(w, h) < 1800:  # upscale small phone-camera shots
        scale = 1800 / max(w, h)
        g = g.resize((int(w * scale), int(h * scale)))
    binarised = g.point(lambda p: 255 if p > 140 else 0)
    return [g, binarised]


def _tesseract_text(image_bytes: bytes) -> str:
    try:
        variants = _preprocess_variants(image_bytes)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Fleet image preprocess failed: {exc}")
        try:
            variants = [Image.open(io.BytesIO(image_bytes))]
        except Exception:  # pylint: disable=broad-exception-caught
            return ""
    # Try each variant across a few page-segmentation modes (columns vs blocks) and
    # keep whichever run captured the most field markers, then the most text.
    best, best_score = "", (-1, -1)
    for img in variants:
        for cfg in ("--psm 6", "--psm 4", ""):
            try:
                t = pytesseract.image_to_string(img, config=cfg)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"Fleet local OCR failed ({cfg or 'default'}): {exc}")
                continue
            score = (len(_MARKER_LINE.findall(t)), len(t.strip()))
            if score > best_score:
                best, best_score = t, score
    return best


def _image_bytes_to_text(image_bytes: bytes) -> str:
    api_text = _vision_api_key_ocr(image_bytes)
    if api_text and api_text.strip():
        return api_text
    return _tesseract_text(image_bytes)


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
_LICENCE_NO = re.compile(r"\b([A-Z9]{4,5}\d{6}[A-Z0-9]{2,8})\b")
# A UK licence line usually starts with its field marker: 1, 2, 3, 4a, 4b, 5, 8, 9…
_FIELD_LINE = re.compile(r"^\s*(\d[a-dA-D]?)\s*[.)\]:]\s*(.*)$")
_URL_TOKEN = re.compile(r"\S*(?:www\.|https?:|\.xyz|\.com|\.co\.uk)\S*", re.IGNORECASE)


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
def _name_words(s: str) -> str:
    """Title-cased alphabetic words only (drops stray OCR punctuation/digits)."""
    return " ".join(w.title() for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", s))


def _collect_licence_fields(lines: List[str]) -> Dict[str, str]:
    """Group licence text by its numbered field markers (1, 2, 3, 4a, 4b, 5, 8, 9…).
    A line with no leading marker is a continuation of the field above it (so a
    multi-line address or a second forename stays attached to its field)."""
    fields: Dict[str, List[str]] = {}
    current = None
    for line in lines:
        m = _FIELD_LINE.match(line)
        if m:
            current = m.group(1).lower()
            fields.setdefault(current, [])
            val = m.group(2).strip()
            if val:
                fields[current].append(val)
        elif current is not None:
            fields[current].append(line.strip())
    return {k: " ".join(v).strip() for k, v in fields.items()}


def parse_driving_licence(text: str) -> Dict[str, str]:
    """Extract driver fields from a UK photocard licence.

    Anchors to the numbered field markers (1 surname, 2 forenames, 3 DOB,
    4a issue, 4b expiry, 5 number, 8 address) so it generalises across licences,
    and falls back to whole-text heuristics wherever a marker didn't OCR cleanly.
    Meant as an editable auto-fill, not a guarantee.
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
    fields = _collect_licence_fields(lines)

    # Name — field 1 (surname) + field 2 (forenames).
    surname = _name_words(fields.get("1", ""))
    forenames = _name_words(fields.get("2", ""))
    result["name"] = " ".join(p for p in [forenames, surname] if p)

    # Dates — anchored to their labels (3 = DOB, 4a = issue, 4b = expiry). Where a
    # label didn't OCR, fall back to the sorted dates: DOB is the earliest and,
    # among the rest, issue is the earliest and expiry the latest.
    def _labelled(key: str):
        ds = _all_dates(fields.get(key, ""))
        return ds[0] if ds else None

    dob, start, end = _labelled("3"), _labelled("4a"), _labelled("4b")
    all_dates = sorted(set(_all_dates(text)))
    if dob is None and all_dates:
        dob = all_dates[0]
    non_dob = [d for d in all_dates if d != dob]
    if start is None and non_dob:
        start = non_dob[0]
    if end is None and non_dob:
        end = non_dob[-1]
    if dob:
        result["dateOfBirth"] = dob.isoformat()
    if start:
        result["licenceStart"] = start.strftime("%d-%m-%Y")
    if end:
        result["licenceEnd"] = end.strftime("%d-%m-%Y")

    # Licence number — field 5, else the DVLA-format search over the whole text,
    # else the first long token on field 5 (handles all-digit template numbers).
    m = _LICENCE_NO.search(fields.get("5", "").upper()) or _LICENCE_NO.search(upper)
    if m:
        result["drivingLicenceNumber"] = m.group(1)
    elif fields.get("5"):
        m2 = re.search(r"[A-Z0-9]{6,}", fields["5"].upper())
        if m2:
            result["drivingLicenceNumber"] = m2.group(0)

    # Address — field 8 block (does NOT require a postcode), else postcode-anchored.
    addr_block = fields.get("8", "")
    if addr_block:
        postcode = _find_postcode(addr_block)
        cleaned = _URL_TOKEN.sub("", addr_block)  # drop template URLs
        if postcode:
            cleaned = re.sub(re.escape(postcode), "", cleaned, flags=re.IGNORECASE)
        result["postcode"] = postcode or _find_postcode(text)
        result["address"] = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.").title()
    else:
        result["postcode"] = _find_postcode(text)
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
