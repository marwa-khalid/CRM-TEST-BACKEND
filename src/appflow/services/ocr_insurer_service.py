"""OCR extraction for Client Insurer (Certificate of Motor Insurance) documents.

Self-contained: pulls text from an uploaded certificate (PDF text layer via
PyMuPDF, tesseract fallback for scanned images) and parses the fields the
Client Insurer & Broker form cares about — insurer company, policyholder,
certificate/policy number, client reference, address + postcode, cover level and
use flags (SDP / private hire).

Works across the ZEGO/Extracover, Nelson and Haven certificate layouts; any field
it can't read is simply returned empty so the form can flag it for manual entry.
"""
from __future__ import annotations

import io
import re
from typing import Dict

import fitz  # PyMuPDF
from PIL import Image
import pytesseract


# ── text extraction ──────────────────────────────────────────────────────────
def extract_certificate_text(file_bytes: bytes, filename: str = "") -> str:
    """Best-effort plain text from a certificate file (never raises)."""
    name = (filename or "").lower()
    is_pdf = name.endswith(".pdf") or file_bytes[:5] == b"%PDF-"
    text = ""
    if is_pdf:
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                parts = [page.get_text() for page in doc]
                text = "\n".join(parts)
                # Scanned PDF (no text layer) → OCR each rendered page.
                if len(text.strip()) < 40:
                    ocr_parts = []
                    for page in doc:
                        pix = page.get_pixmap(dpi=200)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        ocr_parts.append(pytesseract.image_to_string(img))
                    text = "\n".join(ocr_parts)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"insurer OCR: PDF read failed: {exc}")
            text = ""
    else:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(img)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"insurer OCR: image read failed: {exc}")
            text = ""
    return text


# ── field parsing ────────────────────────────────────────────────────────────
_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip(" ,.-\t")


def parse_insurer_certificate(text: str) -> Dict[str, object]:
    """Parse a certificate's text into the Client Insurer form fields."""
    fields: Dict[str, object] = {
        "company_name": "",
        "policy_holder": "",
        "policy_number": "",
        "reference": "",
        "address": "",
        "postcode": "",
        "policy_cover_level": "",
        "sdp": False,
        "private_hire": False,
    }
    if not text:
        return fields
    t = text.replace(" ", " ")
    flat = re.sub(r"[ \t]+", " ", t)

    def find(pattern, group=1, flags=re.I):
        m = re.search(pattern, flat, flags)
        return _clean(m.group(group)) if m else ""

    # Certificate / policy number: "Certificate number: X" | "Certificate No. X" | "Certificate Number X"
    fields["policy_number"] = find(r"Certificate\s*(?:number|no)\.?\s*:?\s*([A-Z0-9][A-Z0-9\-/]{4,})")
    # Fallback for layouts where the label and value are split (e.g. ZEGO): the
    # first dashed/slashed uppercase code on the doc is the certificate number.
    if not fields["policy_number"]:
        m = re.search(r"\b([A-Z]{2,}[A-Z0-9]*[-/][A-Z0-9][A-Z0-9/-]{3,})\b", flat)
        if m:
            fields["policy_number"] = _clean(m.group(1))

    # Client reference (Nelson layout): "Client Reference: 203150"
    fields["reference"] = find(r"Client\s*Reference\.?\s*:?\s*([A-Z0-9][A-Z0-9\-/]+)")

    # Policyholder: "Name of Policyholder: X" | "Policyholder. Mr X" | "Policyholder Mr X"
    holder = find(r"(?:Name\s+of\s+)?Policyholder\.?\s*:?\s*((?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){1,3})", group=2)
    if holder:
        title = find(r"(?:Name\s+of\s+)?Policyholder\.?\s*:?\s*((?:Mr|Mrs|Ms|Miss|Dr)\.?)\s+[A-Z]", group=1)
        fields["policy_holder"] = _clean(f"{title} {holder}") if title else holder

    # Insurer company: the brand word immediately before "Insurance Company
    # Limited/Ltd/Plc" (one leading capitalised word avoids swallowing the
    # surrounding sentence). Title-case ALL-CAPS header matches.
    company = find(r"\b([A-Z][A-Za-z&'.\-]+\s+Insurance\s+Company\s+(?:Limited|Ltd|Plc))\b")
    if company and sum(c.isupper() for c in company if c.isalpha()) > sum(1 for c in company if c.isalpha()) * 0.6:
        company = company.title()
    fields["company_name"] = company

    # Cover level.
    cover = find(r"Cover\s*:?\s*(Comprehensive|Third\s*Party(?:\s*Fire\s*(?:and|&)\s*Theft)?)")
    if cover:
        fields["policy_cover_level"] = "Comprehensive" if "comprehensive" in cover.lower() else "Third Party"

    # Postcode (last one on the doc is usually the insurer's registered office).
    pcs = _POSTCODE.findall(flat)
    if pcs:
        pc = re.sub(r"\s+", " ", pcs[-1]).upper()
        fields["postcode"] = pc
        # Address: text just before that postcode, trimmed of boilerplate labels.
        idx = flat.rfind(pcs[-1])
        pre = flat[max(0, idx - 160):idx]
        pre = re.split(r"(?:Insurance Company (?:Limited|Ltd|Plc)|Registered Office|Authorised Insurers|Address)\s*:?", pre)[-1]
        fields["address"] = _clean(pre)

    # Use flags.
    low = flat.lower()
    fields["private_hire"] = "private hire" in low
    fields["sdp"] = "social, domestic and pleasure" in low or "social domestic and pleasure" in low

    return fields
