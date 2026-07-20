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
            embedded = "\n".join(page.get_text("text") for page in doc).strip()
            if len(embedded) > 80:
                doc.close()
                return embedded
            max_pages = int(os.getenv("FLEET_OCR_MAX_PDF_PAGES", "3"))
            for page in list(doc)[:max_pages]:
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
# Lenient fallback: a postcode-shaped token where OCR mangled a digit into a
# look-alike letter (DD3 -> DDS). Digit slots allow those letters; we map back.
_POSTCODE_LENIENT = re.compile(r"\b([A-Z]{1,2})([0-9OILSZBG]{1,2})([A-Z]?)\s+([0-9OILSZBG])([A-Z]{2})\b")
_LETTER_TO_DIGIT = {"O": "0", "I": "1", "L": "1", "S": "5", "Z": "2", "B": "8", "G": "6"}
# Any postcode-shaped token (mangled or not) to scrub from an address, since the
# corrected postcode is stored separately and the raw form may differ (SWIA vs SW1A).
_PC_ANY = re.compile(r"\b[A-Z]{1,2}[0-9OILSZBG]{1,2}[A-Z]?\s+[0-9OILSZBG][A-Z]{2}\b", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_DATE_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(\d{2,4})\b", re.IGNORECASE)
_MONTH_DATE_MDY = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{2,4})\b", re.IGNORECASE)
_LICENCE_NO = re.compile(r"\b([A-Z9]{4,5}\d{6}[A-Z0-9]{2,8})\b")
# A UK licence line usually starts with its field marker: 1, 2, 3, 4a, 4b, 5, 8, 9…
# Leading `[\s.·•*\-]*` tolerates OCR noise before the marker (e.g. a stray ". 8.").
_FIELD_LINE = re.compile(r"^[\s.·•*\-]*(\d[a-dA-D]?)\s*[.)\]:]\s*(.*)$")
# A field marker sitting at the START of an address value that still needs stripping.
_LEADING_MARKER = re.compile(r"^[\s.·•*\-]*\d{1,2}[a-dA-D]?[.)\]:]\s+")
_URL_TOKEN = re.compile(r"\S*(?:www\.|https?:|\.xyz|\.com|\.co\.uk)\S*", re.IGNORECASE)
_PROOF_NOISE = re.compile(
    r"\b(?:at\s*a\s*glance|start balance|money in|money out|end balance|"
    r"personal account balance|balance in pots|total outgoings|total deposits|"
    r"sort code|account (?:no|number)|swiftbic|bic:|iban)\b.*$",
    re.IGNORECASE,
)


def _find_postcode(text: str) -> str:
    up = text.upper()
    m = _POSTCODE.search(up)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    # Recover an OCR-mangled postcode (e.g. DDS 6PH -> DD5 6PH) so it still gets
    # separated into its own field instead of polluting the address.
    lm = _POSTCODE_LENIENT.search(up)
    if lm:
        area, dist, sub, inw_d, inw_l = lm.groups()
        # Require at least one REAL digit in the original token so all-letter words
        # (e.g. "AS SIX") aren't mistaken for a postcode.
        if any(ch.isdigit() for ch in dist + inw_d):
            dist_fixed = "".join(_LETTER_TO_DIGIT.get(c, c) for c in dist)
            inw_fixed = _LETTER_TO_DIGIT.get(inw_d, inw_d)
            if any(c.isdigit() for c in dist_fixed) and inw_fixed.isdigit():
                return f"{area}{dist_fixed}{sub} {inw_fixed}{inw_l}"
    return ""


def _all_dates(text: str) -> List[date]:
    out: List[date] = []
    for d, mo, y in _DATE.findall(text):
        year = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            out.append(date(year, int(mo), int(d)))
        except ValueError:
            pass
    for y, mo, d in _ISO_DATE.findall(text):
        try:
            out.append(date(int(y), int(mo), int(d)))
        except ValueError:
            pass
    for d, mo, y in _MONTH_DATE_DMY.findall(text):
        month = _MONTHS.get(mo.lower())
        year = int(y) + 2000 if len(y) == 2 else int(y)
        if month:
            try:
                out.append(date(year, month, int(d)))
            except ValueError:
                pass
    for mo, d, y in _MONTH_DATE_MDY.findall(text):
        month = _MONTHS.get(mo.lower())
        year = int(y) + 2000 if len(y) == 2 else int(y)
        if month:
            try:
                out.append(date(year, month, int(d)))
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


def _clean_address(addr: str) -> str:
    """Tidy an OCR'd address:
    - drop symbol garbage like "@ Sees" (a signature / security-feature misread),
    - re-insert a space between a house number and street ("9Anderson" -> "9 Anderson";
      3+ letters so ordinals "1st" and flat suffixes "2B" are left alone),
    - collapse whitespace and stray separators."""
    if not addr:
        return addr
    addr = re.sub(r"@\s*\S+", " ", addr)          # "@ Sees"-type OCR garbage
    addr = _PC_ANY.sub(" ", addr)                  # residual postcode token (SWIA 2AA)
    addr = re.sub(r"[^\w\s,.'/-]", " ", addr)       # any other stray symbols
    addr = re.sub(r"(\d)([A-Za-z]{3,})", r"\1 \2", addr)
    return re.sub(r"\s{2,}", " ", addr).strip(" ,.")


def _clean_proof_segment(seg: str) -> str:
    seg = _PROOF_NOISE.sub("", seg)
    seg = re.sub(r"[•|]+", " ", seg)
    return re.sub(r"\s{2,}", " ", seg).strip(" ,.")


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
        cleaned = _LEADING_MARKER.sub("", cleaned)  # drop any leaked "8." marker
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
                        seg = _LEADING_MARKER.sub("", lines[j])  # strip "8." / ". 8." markers
                        if _DATE.search(seg) or re.search(r"[A-Z9]{4,5}\d{6}", seg.upper()):
                            continue
                        parts.append(seg)
                    addr = re.sub(re.escape(result["postcode"]), "", " ".join(parts), flags=re.IGNORECASE)
                    result["address"] = re.sub(r"\s{2,}", " ", addr).strip(" ,").title()
                    break
    result["address"] = _clean_address(result["address"])
    return result


def parse_proof_of_address(text: str) -> Dict[str, str]:
    """Extract address + postcode from a proof-of-address (bank statement/utility bill)."""
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
            seg = _clean_proof_segment(lines[j])
            if _DATE.search(seg):  # skip a bill/issue date sitting in the block
                continue
            if seg:
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
    result["address"] = _clean_address(result["address"])
    return result


def parse_insurance_certificate(text: str) -> Dict[str, str]:
    """Extract policy start/end dates from an insurance certificate.

    Most certificates label the dates as start/inception/effective/from and
    expiry/end/to. Fall back to the first/last plausible dates in the document.
    """
    result = {"policyStartDate": "", "policyEndDate": ""}
    if not text or not text.strip():
        return result

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    def labelled(pattern: str, prefer_last: bool = False):
        rx = re.compile(pattern, re.IGNORECASE)
        for i, line in enumerate(lines):
            if not rx.search(line):
                continue
            dates = _all_dates(line)
            if dates:
                return dates[-1] if prefer_last else dates[0]
            if i + 1 < len(lines):
                dates = _all_dates(lines[i + 1])
                if dates:
                    return dates[-1] if prefer_last else dates[0]
        return None

    start = labelled(r"\b(?:policy\s*)?(?:start|commencement|inception|effective|from)\b")
    end = labelled(r"\b(?:policy\s*)?(?:end|expiry|expires|expiration|to)\b", prefer_last=True)

    all_dates = sorted(set(_all_dates(text)))
    if start is None and all_dates:
        start = all_dates[0]
    if end is None and all_dates:
        future_or_same = [d for d in all_dates if start is None or d >= start]
        end = future_or_same[-1] if future_or_same else all_dates[-1]

    if start:
        result["policyStartDate"] = start.isoformat()
    if end:
        result["policyEndDate"] = end.isoformat()
    return result


# --------------------------------------------------------------------------- #
# Taxi badge (UK private-hire / hackney carriage driver badge)
# --------------------------------------------------------------------------- #
# Badge numbers vary by council: "25/05927" (Solihull) or "PD12825" (Wolverhampton),
# so accept a letter-prefixed and/or slash-separated alphanumeric token.
_BADGE_NUMBER = re.compile(
    r"(?:licen[cs]e|driver|badge)\s*(?:number|numb\w*|no\.?)?\s*[:\.\-]*\s*"
    r"([A-Z]{0,3}\s?\d[\d/\-\s]{2,12}\d)",
    re.I,
)
_BADGE_NAME = re.compile(
    r"\bname\s*[:\.\-]+\s*([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+){0,3})",
    re.I,
)
_BADGE_EXPIRY = re.compile(
    r"expir\w*\s*(?:date)?\s*[:\.\-]*\s*(\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4})",
    re.I,
)
# Lines that are badge chrome/labels rather than the holder's name.
_NOT_A_NAME = re.compile(
    r"council|licen|number|expir|driver|hire|hackney|badge|system|patent|verify|"
    r"tap|phone|metropolitan|borough|city|private|genuine|date|urbs|rure",
    re.I,
)


def parse_taxi_badge(text: str) -> Dict[str, str]:
    """Extract fields from a UK taxi (private-hire / hackney) driver badge.

    Best-effort like the other parsers: anything it can't read comes back blank so
    the user can type it in. Badges differ a lot between councils, so each field is
    anchored to its label first and only then falls back to a heuristic.
    """
    result = {"badgeNumber": "", "name": "", "expiry": "", "council": "", "badgeType": ""}
    if not text:
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    flat = " ".join(lines)

    match = _BADGE_NUMBER.search(flat)
    if match:
        result["badgeNumber"] = re.sub(r"\s+", "", match.group(1)).strip("/-.")

    # Name — matched per LINE so it can't run on into the next field ("EXPIRY DATE"),
    # and falling back to a standalone name-looking line for badges with no label
    # (e.g. Wolverhampton prints just "Dara Singh").
    for i, line in enumerate(lines):
        match = _BADGE_NAME.search(line)
        if match:
            result["name"] = _name_words(match.group(1))
            break
        if re.match(r"^\s*name\s*[:\.\-]*\s*$", line, re.I) and i + 1 < len(lines):
            result["name"] = _name_words(lines[i + 1])
            break
    if not result["name"]:
        for line in lines:
            if _NOT_A_NAME.search(line):
                continue
            words = re.findall(r"[A-Za-z][A-Za-z'\-]+", line)
            if 2 <= len(words) <= 3 and all(len(w) >= 2 for w in words):
                result["name"] = _name_words(" ".join(words))
                break

    # Expiry: prefer the labelled date, else the latest future-looking date.
    match = _BADGE_EXPIRY.search(flat)
    if match:
        found = _all_dates(match.group(1))
        if found:
            result["expiry"] = found[0].strftime("%d-%m-%Y")
    if not result["expiry"]:
        future = [d for d in _all_dates(flat) if d.year >= date.today().year]
        if future:
            result["expiry"] = max(future).strftime("%d-%m-%Y")

    # Issuing council — the line mentioning "council", joined with the line above
    # when the authority name wraps (e.g. "City of" / "Wolverhampton Council").
    for i, line in enumerate(lines):
        if "council" in line.lower():
            parts = [line]
            prev = lines[i - 1] if i > 0 else ""
            if prev and len(prev) <= 40 and not re.search(r"licen|name|expir|driver|number|hire", prev, re.I):
                parts.insert(0, prev)
            council = re.sub(r"\s+", " ", " ".join(parts)).strip(" .:-")
            result["council"] = council
            break

    low = flat.lower()
    if "hackney" in low:
        result["badgeType"] = "Hackney Carriage Driver"
    elif "private hire" in low:
        result["badgeType"] = "Private Hire Driver"

    return result


# --- Bank transfer receipt -------------------------------------------------
# Receipts differ by bank, and crucially by LAYOUT: statement exports (NatWest,
# Barclays) print the label on one line and the value on the next, while chat-style
# app receipts (Monzo, Revolut) keep them on one line. _label_value handles both.
# Anything unreadable comes back blank for the user to type in.
_RX_AMOUNT_LABEL = re.compile(
    r"\b(?:credit|amount(?:\s+paid)?|total|paid|payment|you\s+sent|sent|transfer(?:red)?)\b", re.I)
_RX_DATE_LABEL = re.compile(
    r"\b(?:date(?:\s+(?:posted|paid|sent))?|paid\s+on|sent\s+on|value\s+date|transaction\s+date)\b", re.I)
# On a credit, the counterparty name is what the bank calls the "description".
_RX_PAYER_LABEL = re.compile(
    r"\b(?:description|from|sender|payer|paid\s+by|account\s+holder)\b", re.I)
_RX_PAYEE_LABEL = re.compile(r"\b(?:payee|recipient|paid\s+to|beneficiary)\b", re.I)
_RX_REFERENCE_LABEL = re.compile(r"\b(?:reference|payment\s+ref\w*|ref(?:\s*(?:no|number))?)\b", re.I)

_RX_MONEY = re.compile(r"(?:GBP|£)?\s*([0-9][0-9,]*(?:\.\d{2})?)", re.I)
_RX_SORT_CODE = re.compile(r"\b(\d{2}[-\s]?\d{2}[-\s]?\d{2})\b")
_RX_ACCOUNT_NO = re.compile(r"\b(\d{8})\b")
_RX_NAMEISH = re.compile(r"[A-Za-z][A-Za-z'&\-]*(?:\s+[A-Za-z0-9'&\-]+){0,5}")
# Lines that are chrome, not values — never treat these as a name.
_RECEIPT_NOISE = re.compile(
    r"^(?:no more information|not available|n/?a|-+|transaction details?|more information)\s*$", re.I)


def _money_str(raw: str) -> str:
    """'£1,250.5' -> '1250.50'; blank when it isn't a number."""
    match = _RX_MONEY.search(raw or "")
    if not match:
        return ""
    try:
        return f"{float(match.group(1).replace(',', '')):.2f}"
    except (TypeError, ValueError):
        return ""


def _label_value(lines: List[str], label: re.Pattern) -> str:
    """Text following a label — same line if present, else the line below.

    The line-below case is what statement PDFs need ("Date posted" / "17 July
    2026"). Noise lines are skipped so a label at the end of a section doesn't
    pick up a heading.
    """
    for i, line in enumerate(lines):
        match = label.search(line)
        if not match:
            continue
        rest = line[match.end():].strip(" :-\t|")
        if rest:
            return rest
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and not _RECEIPT_NOISE.match(nxt):
                return nxt
    return ""


def parse_payment_receipt(text: str) -> Dict[str, str]:
    """Extract payment fields from a bank transfer receipt or statement export."""
    result = {
        "amount": "", "paymentDate": "", "reference": "",
        "payer": "", "payee": "", "sortCode": "", "accountNumber": "",
        "paymentMode": "bank_transfer",
    }
    if not text:
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    flat = " ".join(lines)

    # Amount: the labelled value first, else the largest figure on the receipt
    # (apps print a running balance, which would otherwise win on some layouts).
    result["amount"] = _money_str(_label_value(lines, _RX_AMOUNT_LABEL))
    if not result["amount"]:
        amounts = [a for a in (_money_str(m) for m in re.findall(r"(?:GBP|£)\s*[0-9][0-9,]*(?:\.\d{2})?", flat)) if a]
        if amounts:
            result["amount"] = max(amounts, key=float)

    # Date: the labelled value first, else the latest date that isn't in the future.
    found = _all_dates(_label_value(lines, _RX_DATE_LABEL))
    if found:
        result["paymentDate"] = found[0].strftime("%d-%m-%Y")
    if not result["paymentDate"]:
        past = [d for d in _all_dates(flat) if d <= date.today()]
        if past:
            result["paymentDate"] = max(past).strftime("%d-%m-%Y")

    for key, label in (("payer", _RX_PAYER_LABEL), ("payee", _RX_PAYEE_LABEL),
                       ("reference", _RX_REFERENCE_LABEL)):
        value = _label_value(lines, label)
        if not value:
            continue
        if key == "reference":
            result[key] = re.sub(r"\s+", " ", value).strip(" -_/")
            continue
        match = _RX_NAMEISH.search(value)
        if match:
            result[key] = re.sub(r"\s+", " ", match.group(0)).strip()

    match = _RX_SORT_CODE.search(flat)
    if match:
        digits = re.sub(r"\D", "", match.group(1))
        result["sortCode"] = f"{digits[:2]}-{digits[2:4]}-{digits[4:6]}"

    match = _RX_ACCOUNT_NO.search(flat)
    if match:
        result["accountNumber"] = match.group(1)

    return result
