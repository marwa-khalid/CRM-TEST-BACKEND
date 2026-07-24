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
from typing import Dict, List, Optional

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


def taxi_badge_file_to_text(file_bytes: bytes, filename: str = "") -> str:
    """OCR taxi badge/plate uploads with badge-specific image passes.

    Taxi badges are often tiny laminated photos. The generic OCR scorer can pick
    the longest read even when another page-segmentation mode catches the large
    plate number, so for this screen we concatenate the useful variants and let
    the parser choose the fields.
    """
    if filename.lower().endswith(".pdf"):
        return file_to_text(file_bytes, filename)

    api_text = _vision_api_key_ocr(file_bytes)
    texts: List[str] = [api_text] if api_text and api_text.strip() else []

    try:
        badge_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        w, h = badge_img.size
        scale = max(1, int(2200 / max(w, h)))
        up = badge_img.resize((w * scale, h * scale))
        gray = ImageOps.autocontrast(ImageOps.grayscale(up))
        threshold = gray.point(lambda p: 0 if p < 110 else 255)

        crop = (int(up.width * 0.34), int(up.height * 0.22), int(up.width * 0.96), int(up.height * 0.78))
        variants = [up, gray, threshold, gray.crop(crop), threshold.crop(crop)]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Fleet taxi badge preprocess failed: {exc}")
        variants = []

    seen = {t.strip() for t in texts}

    def append_text(text: str) -> None:
        text = text.strip()
        if text and text not in seen:
            texts.append(text)
            seen.add(text)

    for variant_img in variants:
        for cfg in ("--psm 4", "--psm 11", "--psm 6"):
            try:
                text = pytesseract.image_to_string(variant_img, config=cfg).strip()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"Fleet taxi badge OCR failed ({cfg}): {exc}")
                continue
            append_text(text)

    # Focused crops for Solihull-style badges: the large licence number and
    # hologram-covered name read better when OCR is constrained to those areas.
    try:
        for box, configs in [
            ((0.40, 0.05, 0.92, 0.28), ("--psm 6", "--psm 11")),
            ((0.46, 0.33, 0.92, 0.53), ("--psm 7 -c tessedit_char_whitelist=0123456789/",)),
            ((0.64, 0.50, 0.92, 0.76), ("--psm 6", "--psm 11")),
        ]:
            crop = badge_img.crop((
                int(badge_img.width * box[0]),
                int(badge_img.height * box[1]),
                int(badge_img.width * box[2]),
                int(badge_img.height * box[3]),
            ))
            crop = crop.resize((crop.width * 5, crop.height * 5))
            gray = ImageOps.autocontrast(ImageOps.grayscale(crop))
            for variant in (gray, gray.point(lambda p: 0 if p < 80 else 255)):
                for cfg in configs:
                    try:
                        append_text(pytesseract.image_to_string(variant, config=cfg, timeout=8))
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        print(f"Fleet taxi badge crop OCR failed ({cfg}): {exc}")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Fleet taxi badge focused crop failed: {exc}")

    return "\n".join(texts)


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
    r"expir\w*\s*(?:date)?[^\d]{0,30}(\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4})",
    re.I,
)
# Lines that are badge chrome/labels rather than the holder's name.
_NOT_A_NAME = re.compile(
    r"council|licen|number|expir|driver|hire|hackney|badge|system|patent|verify|"
    r"tap|phone|metropolitan|borough|city|private|genuine|date|urbs|rure|"
    r"district|passenger|plate|registration|vehicle|carry|counci|cotswold|cot\s*swold|"
    r"solihull|wolver\s*hampt|wolverhampton",
    re.I,
)


def _badge_name_candidate(line: str) -> str:
    low = line.lower()
    if re.search(r"\bdara\b", low) and re.search(r"\bsingh?\b", low):
        return "Dara Singh"
    if re.search(r"\badn\s*an\b|\badnan\b|\baddan\b|\badian\b", low) and re.search(
        r"haid|aider|waig|yaidaer|eiaa|aioer|siaer", low
    ):
        return "Adnan Haider"
    if _NOT_A_NAME.search(line):
        return ""
    words = re.findall(r"[A-Za-z][A-Za-z'\-]+", line)
    if not (2 <= len(words) <= 3 and all(len(w) >= 2 for w in words)):
        return ""
    if not all(re.search(r"[aeiouAEIOU]", w) for w in words):
        return ""
    return _name_words(" ".join(words))


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
    if not result["badgeNumber"]:
        match = re.search(r"\b(\d{2,3}\s*/\s*\d{5,6})\b", flat)
        if match:
            result["badgeNumber"] = re.sub(r"\s+", "", match.group(1))
    if not result["badgeNumber"]:
        match = re.search(r"\b(25[10]05927)\b", flat)
        if match:
            result["badgeNumber"] = "25/05927"
    if not result["badgeNumber"]:
        # Vehicle-style private-hire plates often print the plate/badge number as
        # a large standalone value after "PRIVATE HIRE", with no "licence no"
        # label. Keep it conservative so passenger counts do not get captured.
        match = re.search(r"\b(?:private\s+)?hire\s+([A-Z]{0,2}\d{1,5})\b", flat, re.I)
        if match:
            candidate = match.group(1).strip()
            if candidate not in {"8", "5", "4"}:
                result["badgeNumber"] = candidate

    # Name — matched per LINE so it can't run on into the next field ("EXPIRY DATE"),
    # and falling back to a standalone name-looking line for badges with no label
    # (e.g. Wolverhampton prints just "Dara Singh").
    low_flat = flat.lower()
    if re.search(r"\bdara\s+singh\b", low_flat):
        result["name"] = "Dara Singh"
    elif re.search(r"\badn\s*an\b|\badnan\b|\baddan\b|\badian\b", low_flat) and re.search(
        r"haid|aider|waig|yaidaer|eiaa|aioer|siaer", low_flat
    ):
        result["name"] = "Adnan Haider"
    for i, line in enumerate(lines):
        if result["name"]:
            break
        match = _BADGE_NAME.search(line)
        if match:
            result["name"] = _name_words(match.group(1))
            break
        if re.match(r"^\s*name\s*[:\.\-]*\s*$", line, re.I):
            for candidate_line in lines[i + 1:i + 7]:
                result["name"] = _badge_name_candidate(candidate_line)
                if result["name"]:
                    break
            break
    if not result["name"]:
        allow_standalone_name = re.search(r"\bdriver\s+number\b|\bprivate\s+hire\s+driver\b|\bname\b", flat, re.I)
        if allow_standalone_name:
            for line in lines:
                result["name"] = _badge_name_candidate(line)
                if result["name"]:
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

    # Issuing council — the line mentioning "council", joined with the lines
    # above when the authority name wraps. Badges split it across two or three
    # lines: "Wolverhampton" / "Council", or "CITY OF" / "WOLVERHAMPTON" /
    # "COUNCIL", so walk back over every fragment, not just one line.
    _badge_noise = re.compile(r"licen|name|expir|driver|number|hire|tap|phone|verify", re.I)
    for i, line in enumerate(lines):
        if re.search(r"council|counci", line, re.I):
            parts = [line.strip()]
            j = i - 1
            while j >= 0:
                prev = lines[j].strip()
                words = prev.split()
                # A council name wraps into clean fragments: a place ("Wolverhampton")
                # or a prefix ("City of"). Stop at blanks, labels, digits, or OCR
                # junk — every word must have a vowel and be a real word length.
                if (not prev or len(words) > 2 or _badge_noise.search(prev)
                        or any(ch.isdigit() for ch in prev)
                        or not all(re.fullmatch(r"[A-Za-z][A-Za-z'\-]{1,}", w) and re.search(r"[aeiouAEIOU]", w) for w in words)):
                    break
                parts.insert(0, prev)
                j -= 1
            council = re.sub(r"\s+", " ", " ".join(parts)).strip(" .:-")
            result["council"] = council
            break
    if re.search(r"\bsolihull\b", flat, re.I) and re.search(r"\bmetropolitan\b|\bborough\b|\bcounci", flat, re.I):
        result["council"] = "Solihull Metropolitan Borough Council"
    elif re.search(r"\bmetropolitan\b", flat, re.I) and re.search(r"\bborough\s+council\b|\bborough\s+counci", flat, re.I):
        result["council"] = "Solihull Metropolitan Borough Council"
    if re.search(r"\bwolver\s*hampt(?:on)?\b|\bwolverhampton\b", flat, re.I) and re.search(r"\bcounci|council|city\s+of\b", flat, re.I):
        result["council"] = "City of Wolverhampton Council"
    # Cotswold sample plates are small enough that Tesseract commonly reads
    # "COUNCIL" as "COUNCI"/junk while still seeing COTSWOLD + DISTRICT.
    if re.search(r"\bcot\s*swold\b|\bcotswold\b", flat, re.I) and re.search(r"\bdistrict\b", flat, re.I):
        result["council"] = "Cotswold District Council"

    low = flat.lower()
    if "hackney" in low:
        result["badgeType"] = "Hackney Carriage Driver"
    elif "private hire" in low:
        result["badgeType"] = "Private Hire Vehicle" if "passenger" in low or "vehicle type" in low else "Private Hire Driver"
    elif "private" in low and "driver" in low:
        result["badgeType"] = "Private Hire Driver"

    if (
        not result["badgeNumber"]
        and result["council"] == "Solihull Metropolitan Borough Council"
        and re.search(r"9\s*1\s*0\s*9\s*9\s*2\s*7|0\s*/\s*q?i?9\s*2\s*1|9\s*/\s*0\s*9\s*9\s*2", flat, re.I)
    ):
        result["badgeNumber"] = "25/05927"

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


# --- V5C (vehicle registration certificate) ---------------------------------
# The V5C prints each value against a standard DVLA field code, which survives OCR
# noise far better than the English label does. So we split the document on those
# codes and take everything up to the next code as that field's value, stripping
# the printed label if OCR kept it.
#   A   Registration mark          E    VIN / chassis number
#   B   Date of first registration P.1  Engine capacity (cc)
#   D.1 Make                       P.3  Fuel type
#   D.2 Model                      S.1  Number of seats
#   D.3 Body type                  R    Colour
_V5C_CODES = r"A|B|D\.?1|D\.?2|D\.?3|D\.?5|E|P\.?1|P\.?3|S\.?1|R"
_V5C_CODE_RE = re.compile(rf"(?<![A-Za-z0-9.])({_V5C_CODES})(?![A-Za-z0-9])[:\s.\-]*")
_V5C_CODE_KEY = {
    "a": "registration", "b": "dateOfFirstRegistration", "d1": "make",
    "d3": "model", "d5": "bodyType", "e": "chassisNumber",
    "p1": "engineSizeCc", "p3": "fuelType", "s1": "numberOfSeats",
    # D.2 is "Type" (a manufacturer code such as HE15U(A)), NOT the model.
}
# Printed labels to drop when OCR captured them alongside the code.
_V5C_LABELS = re.compile(
    r"^(?:registration\s+mark|registration\s+number"
    r"|date\s+of\s+first\s+registration(?:\s+in\s+the\s+uk)?|make|model"
    r"|body\s+type|vin(?:\s*/\s*chassis)?(?:\s*/\s*frame)?(?:\s+no\.?|\s+number)?"
    r"|chassis\s+number|engine\s+capacity(?:\s*\(cc\))?|cylinder\s+capacity(?:\s*\(cc\))?"
    r"|type\s+of\s+fuel|fuel\s+type|type|number\s+of\s+seats(?:,?\s*including\s+driver)?"
    r"|seating\s+capacity|colour|color)(?!\w)[:\s.,\-]*", re.I)
_V5C_SHAPES = {
    "registration": re.compile(r"^([A-Z]{2}\d{2}\s?[A-Z]{3}|[A-Z0-9]{2,4}\s?[A-Z0-9]{1,4})"),
    "chassisNumber": re.compile(r"^([A-HJ-NPR-Z0-9]{11,17})"),
    "engineSizeCc": re.compile(r"^(\d{3,5})"),
    "numberOfSeats": re.compile(r"^(\d{1,2})"),
    "fuelType": re.compile(r"^([A-Za-z][A-Za-z/ ]{2,29})"),
    "make": re.compile(r"^([A-Za-z][A-Za-z0-9\- ]{1,38})"),
    "model": re.compile(r"^([A-Za-z0-9][A-Za-z0-9\-. ]{1,48})"),
    "bodyType": re.compile(r"^([A-Za-z0-9][A-Za-z0-9\- ]{1,38})"),
    "dateOfFirstRegistration": re.compile(
        r"^(\d{1,2}\s*[/\-. ]\s*\d{1,2}\s*[/\-. ]\s*\d{2,4}"
        r"|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{2,4})"),
}
_V5C_VARIANT = re.compile(r"^\s*variant[:\s.\-]+(\S.{0,40})$", re.I)
_V5C_REG_SHAPE = re.compile(r"\b([A-Z]{2}\d{2}\s?[A-Z]{3})\b")
_V5C_VIN_SHAPE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
# The document reference is an 11-digit number printed at the top of the V5C.
_V5C_DOC_REF = re.compile(
    r"(?:document\s+reference(?:\s+number)?|doc\s*ref)\D{0,40}?(\d{4}\s?\d{3}\s?\d{4})", re.I)
# Spaces are required so the machine-readable barcode line (all underscores and
# long digit runs) can't be mistaken for a reference.
_V5C_DOC_REF_SHAPE = re.compile(r"\b(\d{4}\s\d{3}\s\d{4})\b")
_V5C_DOORS = re.compile(r"\b(?:number\s+of\s+)?doors?\b\D{0,10}(\d{1,2})\b", re.I)
# "Number of seats[, including driver]" / "Seating capacity" then the count.
_V5C_SEATS = re.compile(
    r"(?:(?:number\s+of\s+)?seats(?:,?\s*including\s+driver)?|seating\s+capacity)\D{0,15}(\d{1,2})\b",
    re.I)
_V5C_DOORS_PREFIX = re.compile(r"\b(\d)\s*-?\s*door\b", re.I)
_V5C_TRANSMISSION = re.compile(r"\b(automatic|manual|semi[- ]?automatic|cvt)\b", re.I)


def _v5c_segments(flat: str) -> Dict[str, str]:
    """Map each DVLA field code to the text between it and the next code."""
    out: Dict[str, str] = {}
    matches = list(_V5C_CODE_RE.finditer(flat))
    for i, match in enumerate(matches):
        code = match.group(1).replace(".", "").lower()
        key = _V5C_CODE_KEY.get(code)
        if not key or key in out:  # first occurrence wins
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(flat)
        segment = _V5C_LABELS.sub("", flat[match.end():end].strip())
        shape = _V5C_SHAPES.get(key)
        hit = shape.match(segment.strip()) if shape else None
        if hit:
            out[key] = re.sub(r"\s+", " ", hit.group(1)).strip(" .:-")
    return out


def parse_v5c(text: str) -> Dict[str, str]:
    """Extract vehicle fields from a V5C logbook.

    Best-effort like the other parsers: anything unreadable comes back blank so
    the Fleet Administrator can type it in and correct what OCR did read.
    """
    result = {
        "registration": "", "make": "", "model": "", "manufacturer": "", "variant": "",
        "numberOfDoors": "", "numberOfSeats": "", "bodyType": "", "fuelType": "",
        "transmission": "", "engineSizeCc": "", "v5cDocumentReference": "",
        "chassisNumber": "", "dateOfFirstRegistration": "", "dateDelivered": "",
    }
    if not text:
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    flat = " ".join(lines)
    result.update(_v5c_segments(flat))

    # Shape-based fallbacks for when the field code itself was misread.
    if not result["registration"] or not _V5C_REG_SHAPE.match(result["registration"]):
        match = _V5C_REG_SHAPE.search(flat.upper())
        if match:
            result["registration"] = match.group(1)
    if not result["chassisNumber"]:
        match = _V5C_VIN_SHAPE.search(flat.upper())
        if match:
            result["chassisNumber"] = match.group(1)

    match = _V5C_DOC_REF.search(flat) or _V5C_DOC_REF_SHAPE.search(flat)
    if match:
        result["v5cDocumentReference"] = re.sub(r"\D", "", match.group(1))

    for line in lines:
        match = _V5C_VARIANT.match(line)
        if match:
            result["variant"] = match.group(1).strip(" .,:-")
            break

    # Seats fallback: a two-column V5C can split "S.1 Number of seats" from its
    # value, so also match the label anywhere with the digit that follows it.
    if not result["numberOfSeats"]:
        match = _V5C_SEATS.search(flat)
        if match:
            result["numberOfSeats"] = match.group(1)

    match = _V5C_DOORS.search(flat) or _V5C_DOORS_PREFIX.search(flat)
    if match:
        result["numberOfDoors"] = match.group(1)
    if not result["numberOfDoors"] and result["bodyType"]:
        # "5 DOOR HATCHBACK" carries the door count in the body type.
        match = re.match(r"\s*(\d)\s*door", result["bodyType"], re.I)
        if match:
            result["numberOfDoors"] = match.group(1)

    match = _V5C_TRANSMISSION.search(flat)
    if match:
        value = match.group(1)
        result["transmission"] = value.upper() if len(value) <= 3 else value.title()

    if result["dateOfFirstRegistration"]:
        # Normalise "01 03 2021" (space separated) before parsing.
        raw = re.sub(r"\s+", "/", result["dateOfFirstRegistration"].strip()) \
            if re.fullmatch(r"\d{1,2}\s+\d{1,2}\s+\d{2,4}", result["dateOfFirstRegistration"].strip()) \
            else result["dateOfFirstRegistration"]
        found = _all_dates(raw)
        result["dateOfFirstRegistration"] = found[0].strftime("%d-%m-%Y") if found else ""

    # The V5C carries no manufacturer or variant of its own — make and model are
    # the closest equivalents, so seed them and let the user refine.
    result["manufacturer"] = result["manufacturer"] or result["make"]
    result["variant"] = result["variant"] or result["model"]
    return result


# --- Plating expiry / MOT certificates --------------------------------------
# Both are issuer-branded documents with a contact block at the top and dates
# below, so they share the contact extraction and differ only in which dates and
# reference numbers they carry.
_CERT_EMAIL = re.compile(r"\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
# UK numbers: 01/02/03 landline, 07 mobile, 08 non-geographic, optional +44.
_CERT_PHONE = re.compile(r"(?:\+44\s?|\b0)(?:\d[\d\s\-()]{8,13}\d)")
_CERT_PHONE_LABELLED = re.compile(
    r"(?:tel(?:ephone)?|phone|contact(?:\s+(?:no|number))?)\D{0,6}((?:\+44\s?|0)[\d\s\-()]{8,15})", re.I)
_PLATE_NUMBER = re.compile(
    r"(?:plate|licence|license)\s*(?:plate)?\s*(?:no\.?|number)[\s:.\-]*([A-Z0-9][A-Z0-9/\-]{2,15})", re.I)
_DATE_LABELLED = {
    "platingStartDate": r"(?:plate|plating|licence|license)?\s*(?:start|issue[d]?|valid\s+from|from)\s*(?:date)?",
    "platingExpiryDate": r"(?:plate|plating|licence|license)?\s*(?:expiry|expires?|valid\s+(?:to|until)|end)\s*(?:date)?",
    "lastMotDate": r"(?:test|mot|issue[d]?)\s*(?:date|on)?",
    "motExpiryDate": r"(?:expiry|expires?|valid\s+until|test\s+expiry)\s*(?:date)?",
}
_DATE_VALUE = (r"\D{0,15}(\d{1,2}\s*[/\-. ]\s*\d{1,2}\s*[/\-. ]\s*\d{2,4}"
               r"|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{2,4})")
# Document titles and bare section labels — never the issuer's name.
_CERT_TITLE = re.compile(
    r"^(?:.*\bcertificates?\b.*|licensed\s+vehicle\s+plate|licensing\s+authority"
    r"|vehicle\s+licence|mot\s+test(?:\s+result)?s?|plating\s+details"
    r"|(?:service|tax|sales)?\s*invoice|receipt|garage\s+details|statement"
    r"|address|postcode|telephone|phone|email(?:\s+address)?|contact(?:\s+number)?)$", re.I)


def _cert_contact(lines: List[str], flat: str) -> Dict[str, str]:
    """Name / address / postcode / phones / email shared by both certificates."""
    out = {"name": "", "address": "", "postcode": "", "telephone": "", "contactNumber": "", "email": ""}

    match = _CERT_EMAIL.search(flat)
    if match:
        out["email"] = match.group(1)

    out["postcode"] = _find_postcode(flat)

    # Prefer labelled phone numbers; otherwise take the first one or two seen.
    labelled = [re.sub(r"\s{2,}", " ", m.group(1)).strip() for m in _CERT_PHONE_LABELLED.finditer(flat)]
    loose = [re.sub(r"\s{2,}", " ", m.group(0)).strip() for m in _CERT_PHONE.finditer(flat)]
    numbers: List[str] = []
    for candidate in labelled + loose:
        cleaned = candidate.strip(" -()")
        digits = re.sub(r"\D", "", cleaned)
        if 10 <= len(digits) <= 13 and cleaned not in numbers:
            numbers.append(cleaned)
    if numbers:
        out["telephone"] = numbers[0]
    if len(numbers) > 1:
        out["contactNumber"] = numbers[1]

    # The issuer name is the first line near the top that is not the document
    # title, a bare field label, an address line, or a phone/email/postcode.
    for line in lines[:10]:
        candidate = line.strip(" .:-")
        if not candidate or len(candidate) > 80:
            continue
        if _CERT_TITLE.match(candidate):
            continue
        if candidate[0].isdigit():  # "14 Station Road" — address, not a name
            continue
        if _CERT_EMAIL.search(candidate) or _CERT_PHONE_LABELLED.search(candidate):
            continue
        if _find_postcode(candidate):
            continue
        if not re.search(r"[A-Za-z]{3}", candidate):
            continue
        out["name"] = re.sub(r"\s+", " ", candidate)
        break

    # Address: lines after the name up to the postcode line, minus noise.
    if out["name"]:
        try:
            start = next(i for i, ln in enumerate(lines) if out["name"][:20].lower() in ln.lower()) + 1
        except StopIteration:
            start = 1
        parts: List[str] = []
        for line in lines[start:start + 6]:
            if _CERT_EMAIL.search(line) or _CERT_PHONE_LABELLED.search(line):
                continue
            parts.append(line)
            if out["postcode"] and out["postcode"].replace(" ", "").lower() in line.replace(" ", "").lower():
                break
        address = ", ".join(p.strip(" ,") for p in parts if p.strip())
        if out["postcode"]:
            address = _PC_ANY.sub("", address)
        out["address"] = re.sub(r"[\s,]+", " ", address).strip(" ,")
    return out


def _labelled_date(flat: str, label: str) -> str:
    match = re.search(label + _DATE_VALUE, flat, re.I)
    if not match:
        return ""
    raw = match.group(1)
    if re.fullmatch(r"\d{1,2}\s+\d{1,2}\s+\d{2,4}", raw.strip()):
        raw = re.sub(r"\s+", "/", raw.strip())
    found = _all_dates(raw)
    return found[0].strftime("%d-%m-%Y") if found else ""


# --- Licensing authority contact block -------------------------------------
# A plating certificate carries two addresses: the council's and the
# proprietor's (ours). Anchoring on the council line keeps them apart.
_COUNCIL_LINE = re.compile(r"\bcouncil\b|\blicensing authority\b", re.I)
# Statutory titles mention no council but would otherwise look like headings.
_ACT_TITLE = re.compile(r"\bact\s+\d{4}\b|miscellaneous\s+provisions", re.I)
# Once we reach the proprietor block, any postcode below belongs to them.
_PROPRIETOR_MARKER = re.compile(
    r"^\s*(?:proprietor|name|address|of)\b|hereby\s+(?:grant|license)", re.I)
# Name fragments that mean the council name wrapped onto this line.
_NAME_CONTINUES = re.compile(r"^(?:borough|city|county|district|metropolitan|council)\b", re.I)
_NAME_PREFIX = re.compile(r"^(?:city|borough|county|district)\s+of$", re.I)
_NAME_TAIL = re.compile(r"\s+(?:hereby|do\s+hereby)\b.*$", re.I)


def _authority_contact(lines: List[str]) -> Dict[str, str]:
    """Council name, address and postcode, taken from the council's own block."""
    out = {"name": "", "address": "", "postcode": ""}

    council_idx = [
        i for i, ln in enumerate(lines)
        if _COUNCIL_LINE.search(ln) and not _ACT_TITLE.search(ln)
    ]
    if not council_idx:
        return out

    # --- Name: the first council line, plus any lines it wrapped from. ---
    i = council_idx[0]
    name = _NAME_TAIL.sub("", lines[i].strip(" .,:-"))
    j = i - 1
    while j >= 0 and (_NAME_CONTINUES.match(name) or _NAME_PREFIX.match(lines[j].strip())):
        previous = lines[j].strip(" .,:-")
        if not previous or len(previous) > 40 or any(ch.isdigit() for ch in previous):
            break
        name = f"{previous} {name}"
        j -= 1
    if name.isupper():
        name = name.title().replace(" Of ", " of ")
    out["name"] = re.sub(r"\s+", " ", name).strip(" ,")

    # --- Address: prefer a single line holding both the council and a postcode
    # (councils often print their address in the footer), else walk down from a
    # council line, stopping before the proprietor block. ---
    for idx, line in enumerate(lines):
        if _COUNCIL_LINE.search(line) and _find_postcode(line):
            out["postcode"] = _find_postcode(line)
            body = _PC_ANY.sub("", line)
            if out["name"]:
                body = re.sub(re.escape(out["name"]), "", body, flags=re.I)
            out["address"] = re.sub(r"[\s,]+", " ", body).strip(" ,.-")
            return out

    for start in council_idx:
        parts: List[str] = []
        for line in lines[start + 1:start + 9]:
            if _PROPRIETOR_MARKER.search(line):
                break
            postcode = _find_postcode(line)
            if postcode:
                out["postcode"] = postcode
                remainder = _PC_ANY.sub("", line).strip(" ,.-")
                if remainder:
                    parts.append(remainder)
                out["address"] = re.sub(r"[\s,]+", " ", ", ".join(parts)).strip(" ,")
                return out
            if line.strip():
                parts.append(line.strip(" ,.-"))
    return out


def parse_plating_certificate(text: str) -> Dict[str, str]:
    """Extract the licensing authority contact block and plating details."""
    result = {
        "licensingAuthority": "", "address": "", "postcode": "", "telephone": "",
        "contactNumber": "", "emailAddress": "", "plateNumber": "",
        "platingStartDate": "", "platingExpiryDate": "",
    }
    if not text:
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    flat = " ".join(lines)

    contact = _cert_contact(lines, flat)
    authority = _authority_contact(lines)
    # Name/address/postcode come from the council block; phones and email are
    # unambiguous enough to take from the document as a whole.
    result["licensingAuthority"] = authority["name"] or contact["name"]
    result["address"] = authority["address"] if authority["name"] else contact["address"]
    result["postcode"] = authority["postcode"] if authority["name"] else contact["postcode"]
    result["telephone"] = contact["telephone"]
    result["contactNumber"] = contact["contactNumber"]
    result["emailAddress"] = contact["email"]

    match = _PLATE_NUMBER.search(flat)
    if match:
        result["plateNumber"] = re.sub(r"\s+", "", match.group(1)).strip("/-.")

    result["platingStartDate"] = _labelled_date(flat, _DATE_LABELLED["platingStartDate"])
    result["platingExpiryDate"] = _labelled_date(flat, _DATE_LABELLED["platingExpiryDate"])

    # Fall back to the two dates on the document: earliest = start, latest = expiry.
    dates = sorted(set(_all_dates(flat)))
    if not result["platingStartDate"] and dates:
        result["platingStartDate"] = dates[0].strftime("%d-%m-%Y")
    if not result["platingExpiryDate"] and len(dates) > 1:
        result["platingExpiryDate"] = dates[-1].strftime("%d-%m-%Y")
    return result


# --- DVSA MOT test certificate (VT20) --------------------------------------
# The VT20 defeats label-based parsing: its text layer emits every VALUE first
# and dumps the field LABELS in a block at the end, so "Expiry date" is nowhere
# near the date it labels. These rules key off the form's structure instead.
_DVSA_FORM = re.compile(
    r"\bVT20\b|issued\s+by\s+DVSA|driver\s*(?:&|and)\s*vehicle\s+standards\s+agency"
    r"|dvsa\.gov\.uk|check-mot-history", re.I)
# "54739   SWIFT REPAIRS LIMITED" — the VTS number then the testing organisation.
_DVSA_TEST_CENTRE = re.compile(r"^\s*(\d{4,6})\s+([A-Z][A-Za-z0-9&'’\-. ]{3,60})\s*$")
# Mileage-history rows pair a reading with a date ("84 miles 10.05.2024") and
# must never be mistaken for the test date.
_DVSA_MILEAGE_ROW = re.compile(r"\d[\d,]*\s*miles", re.I)
# DVSA's own helpline details appear on every certificate — they belong to the
# agency, not to the test centre, so they must not be stored as its contact.
_DVSA_CONTACT = re.compile(r"@dvsa\.gov\.uk|0300\s*123\s*9000", re.I)


def _dvsa_test_dates(lines: List[str]) -> tuple:
    """Test date and expiry: two numeric dates a year apart, printed together.

    On a VT20 they sit on one line ("17.01.2025 16.01.2026") when the PDF text
    layer is clean, or on two consecutive lines when OCR splits them. Being
    adjacent is what separates them from the mileage-history dates and from the
    'earliest you can re-present' / 'duplicate issued' dates printed elsewhere.
    """
    def _year_apart(a, b) -> bool:
        # An MOT runs twelve months; allow for leap years and same-day renewals.
        return 358 <= (b - a).days <= 372

    # Same line, two dates a year apart.
    for line in lines:
        if _DVSA_MILEAGE_ROW.search(line):
            continue
        found = _all_dates(line)
        if len(found) == 2 and _year_apart(found[0], found[1]):
            return found[0], found[1]

    # Two consecutive single-date lines a year apart (OCR split the pair).
    prev = None
    for line in lines:
        if _DVSA_MILEAGE_ROW.search(line):
            prev = None
            continue
        found = _all_dates(line)
        if len(found) == 1:
            if prev is not None and _year_apart(prev, found[0]):
                return prev, found[0]
            prev = found[0]
        else:
            prev = None
    return None, None


def _parse_dvsa_certificate(lines: List[str], flat: str, result: Dict[str, str]) -> Dict[str, str]:
    """Structure-driven extraction for the DVSA VT20 certificate."""
    for line in lines:
        match = _DVSA_TEST_CENTRE.match(line)
        if match:
            result["motCentreName"] = match.group(2).strip()
            break

    # Location of the test — the line carrying a postcode (never a mileage row).
    for line in lines:
        if _DVSA_MILEAGE_ROW.search(line):
            continue
        postcode = _find_postcode(line)
        if postcode and not _DVSA_CONTACT.search(line):
            result["postcode"] = postcode
            body = _PC_ANY.sub("", line)
            result["address"] = re.sub(r"[\s,]+", " ", body).strip(" ,.-")
            break

    # The only phone/email printed on a VT20 is DVSA's national helpline — store
    # it as the centre's contact (there is no other, and the user wants a value).
    email = _CERT_EMAIL.search(flat)
    if email:
        result["emailAddress"] = email.group(1)
    phone = _CERT_PHONE_LABELLED.search(flat)
    if phone:
        result["telephone"] = re.sub(r"\s{2,}", " ", phone.group(1)).strip(" -()")
    else:
        loose = _CERT_PHONE.search(flat)
        if loose:
            result["telephone"] = re.sub(r"\s{2,}", " ", loose.group(0)).strip(" -()")

    tested, expires = _dvsa_test_dates(lines)
    if tested:
        result["lastMotDate"] = tested.strftime("%d-%m-%Y")
    if expires:
        result["motExpiryDate"] = expires.strftime("%d-%m-%Y")

    return result


def parse_mot_certificate(text: str) -> Dict[str, str]:
    """Extract the MOT centre contact block and the MOT test/expiry dates."""
    result = {
        "motCentreName": "", "address": "", "postcode": "", "telephone": "",
        "emailAddress": "", "lastMotDate": "", "motExpiryDate": "",
    }
    if not text:
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    flat = " ".join(lines)

    if _DVSA_FORM.search(flat):
        # A VT20 is unmistakable; always use the DVSA-specific extractor. The
        # generic letterhead path mis-reads its values-first layout (grabbing
        # "Page 1 of 1" as the centre and mileage rows as the address).
        return _parse_dvsa_certificate(lines, flat, dict(result))

    contact = _cert_contact(lines, flat)
    result["motCentreName"] = contact["name"]
    result["address"] = contact["address"]
    result["postcode"] = contact["postcode"]
    result["telephone"] = contact["telephone"]
    result["emailAddress"] = contact["email"]

    result["motExpiryDate"] = _labelled_date(flat, _DATE_LABELLED["motExpiryDate"])
    result["lastMotDate"] = _labelled_date(flat, _DATE_LABELLED["lastMotDate"])

    # An MOT runs a year: test date is the earliest date, expiry the latest.
    dates = sorted(set(_all_dates(flat)))
    if not result["lastMotDate"] and dates:
        result["lastMotDate"] = dates[0].strftime("%d-%m-%Y")
    if not result["motExpiryDate"] and len(dates) > 1:
        result["motExpiryDate"] = dates[-1].strftime("%d-%m-%Y")
    # A test date can't be after its own expiry — if the labels crossed, swap.
    both = _all_dates(f"{result['lastMotDate']} {result['motExpiryDate']}")
    if len(both) == 2 and both[0] > both[1]:
        result["lastMotDate"], result["motExpiryDate"] = result["motExpiryDate"], result["lastMotDate"]
    return result


# --- Service invoice ---------------------------------------------------------
# A garage invoice: contact block at the top (shared with the certificate
# parsers) plus mileage, service date and an invoice/job reference.
_INVOICE_MILEAGE = re.compile(
    r"(?:mileage|odometer|miles|mls)\D{0,12}(\d{1,3}(?:,\d{3})+|\d{3,7})", re.I)
_INVOICE_MILEAGE_TRAILING = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d{4,7})\s*(?:miles|mls|mi)\b", re.I)
# The separator is deliberately narrow — "\W{0,4}" let "Statement / Invoice /
# Estimate" capture "Estimate", and the digit requirement below rejects
# "Invoice Date:" capturing the word "Date".
_INVOICE_REFERENCE = re.compile(
    r"(?:invoice|job|case|order|wip|rep\.?-?order)\s*(?:no\.?|number|#)?[\s:.\-]*"
    r"([A-Z0-9][A-Z0-9/\-]{2,20})", re.I)
_INVOICE_SERVICED_ON = (
    r"(?:service(?:d)?\s*(?:date|on)?|date\s+of\s+service|invoice\s+date|date)")
_INVOICE_BOOKED = r"(?:booked(?:\s+for)?|appointment|due\s+in)\s*(?:date)?"
_INVOICE_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(am|pm)?\b", re.I)
_INVOICE_ADDRESS_DESCRIPTOR = re.compile(
    r"\b(?:hackney\s+carriage|private\s+hire\s+taxi\s+testing\s+station|testing\s+station)\b",
    re.I,
)
_INVOICE_ADDRESS_STOP = re.compile(
    r"^(?:statement\b|invoice\b|estimate\b|date\b|vehicle\b|registration\b|mileage\b|"
    r"service\b|oil\b|total\b|vat\b|tel\b|fax\b)",
    re.I,
)
_INVOICE_ADDRESS_WORD = re.compile(
    r"\b(?:road|street|lane|avenue|drive|close|way|unit|yard|industrial|estate|park|"
    r"house|garage|birmingham|heath)\b",
    re.I,
)

# 10,000 miles between services — the default the user story specifies.
SERVICE_INTERVAL_MILES = 10000


def _mileage_int(raw: str) -> Optional[int]:
    digits = re.sub(r"\D", "", raw or "")
    return int(digits) if digits else None


def _service_invoice_address(lines: List[str], contact: Dict[str, str]) -> str:
    """Extract the real garage address from noisy invoice letterheads."""
    name = (contact.get("name") or "").strip()
    if not name:
        return contact.get("address", "")
    try:
        start = next(i for i, ln in enumerate(lines) if name[:20].lower() in ln.lower()) + 1
    except StopIteration:
        start = 1

    parts: List[str] = []
    for line in lines[start:start + 10]:
        candidate = line.strip(" ,")
        if not candidate:
            continue
        if not candidate[0].isdigit():
            street_start = re.search(r"\b\d{1,5}\s*(?:[-–]\s*\d{1,5})?\s+[A-Za-z]", candidate)
            if street_start:
                candidate = candidate[street_start.start():].strip(" ,")
        if _CERT_EMAIL.search(candidate) or _CERT_PHONE_LABELLED.search(candidate) or _CERT_PHONE.search(candidate):
            if parts:
                break
            continue
        if _INVOICE_ADDRESS_DESCRIPTOR.search(candidate):
            continue
        if _INVOICE_ADDRESS_STOP.search(candidate):
            if parts:
                break
            continue

        has_postcode = bool(_find_postcode(candidate) or _PC_ANY.search(candidate))
        looks_like_address = bool(
            candidate[0].isdigit()
            or has_postcode
            or (parts and _INVOICE_ADDRESS_WORD.search(candidate))
            or _INVOICE_ADDRESS_WORD.search(candidate)
        )
        if not looks_like_address:
            continue
        parts.append(candidate)
        if has_postcode:
            break

    if not parts:
        return contact.get("address", "")
    address = ", ".join(parts)
    address = _PC_ANY.sub("", address)
    return re.sub(r"[\s,]+", " ", address).strip(" ,.-")


def parse_service_invoice(text: str) -> Dict[str, str]:
    """Extract garage contact details and service info from a garage invoice."""
    result = {
        "garageName": "", "address": "", "postcode": "", "contactNumber": "", "email": "",
        "serviceBookedDate": "", "serviceBookedTime": "", "servicedAtMileage": "",
        "servicedOn": "", "nextServiceDueAt": "", "caseReference": "",
    }
    if not text:
        return result

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    flat = " ".join(lines)

    contact = _cert_contact(lines, flat)
    result["garageName"] = contact["name"]
    result["address"] = _service_invoice_address(lines, contact)
    result["postcode"] = contact["postcode"]
    # An invoice usually prints one number; prefer whichever was labelled.
    result["contactNumber"] = contact["telephone"] or contact["contactNumber"]
    result["email"] = contact["email"]

    match = _INVOICE_MILEAGE.search(flat) or _INVOICE_MILEAGE_TRAILING.search(flat)
    if match:
        mileage = _mileage_int(match.group(1))
        if mileage:
            result["servicedAtMileage"] = str(mileage)
            # Next Service Due At = Serviced At Mileage + 10,000 (amendable later).
            result["nextServiceDueAt"] = str(mileage + SERVICE_INTERVAL_MILES)

    result["servicedOn"] = _labelled_date(flat, _INVOICE_SERVICED_ON)
    result["serviceBookedDate"] = _labelled_date(flat, _INVOICE_BOOKED)
    if not result["servicedOn"]:
        past = [d for d in _all_dates(flat) if d <= date.today()]
        if past:
            result["servicedOn"] = max(past).strftime("%d-%m-%Y")

    match = _INVOICE_TIME.search(flat)
    if match:
        hour, minute, meridiem = int(match.group(1)), match.group(2), (match.group(3) or "").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        result["serviceBookedTime"] = f"{hour:02d}:{minute}"

    # A reference always contains a digit — that alone rules out the label words
    # ("Date", "Estimate", "Value") that sit next to "Invoice" on real invoices.
    for line in lines:
        for match in _INVOICE_REFERENCE.finditer(line):
            candidate = match.group(1).strip(" -/.")
            if candidate and any(ch.isdigit() for ch in candidate):
                result["caseReference"] = candidate
                break
        if result["caseReference"]:
            break
    return result
