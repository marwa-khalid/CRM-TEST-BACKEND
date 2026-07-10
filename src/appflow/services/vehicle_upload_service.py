import os
import urllib.parse
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
import numpy as np
import json
from sqlalchemy.orm import Session
import mimetypes
from datetime import datetime,timezone
from libdata.enums import HistoryLogType
from libdata.models.tables import HistoryActivities, Claim
from appflow.utils import build_case_reference
import io
import re
from typing import List, Dict, Any
from google.cloud import vision
from dateutil import parser as dateparser
import tempfile
from pdf2image import convert_from_path
from appflow.services.s3_service import S3Service
from libdata.models.tables import CaseDocument
from appflow.services.google_vision_auth import (
    configure_google_vision_credentials,
    ocr_image_with_api_key,
)

configure_google_vision_credentials()
client = vision.ImageAnnotatorClient()
_easyocr_reader = None


def get_easyocr_reader():
    """Lazy EasyOCR fallback for cases where Vision/Tesseract returns no text."""
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(["en"])
    return _easyocr_reader

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Poppler path configuration for PDF processing
POPPLER_PATH = os.environ.get("POPPLER_PATH")
if not POPPLER_PATH and os.path.exists("/usr/bin/pdfinfo"):
    POPPLER_PATH = "/usr/bin"

def _history_base_dir():
    return os.path.abspath(os.path.join(os.getcwd(), "uploads", "history"))

# ---------- Google Vision OCR Functions ----------
def extract_text_with_tesseract(image_path: str) -> str:
    """Fallback OCR using local Tesseract when Google Vision is unavailable.

    Kept identical to the engineer screen's approach (a plain full-image read)
    rather than layout-specific cropping, which was tuned for one V5C layout
    and mangled others.
    """
    try:
        with Image.open(image_path) as img:
            return pytesseract.image_to_string(img)
    except Exception as exc:
        print(f"Warning: Local OCR failed for {image_path}: {exc}")
        return ""


def extract_text_with_easyocr(image_path: str) -> str:
    """Final OCR fallback using EasyOCR when other engines return no text."""
    try:
        with Image.open(image_path) as img:
            img_np = np.array(img)
        return "\n".join(result[1] for result in get_easyocr_reader().readtext(img_np))
    except Exception as exc:
        print(f"Warning: EasyOCR failed for {image_path}: {exc}")
        return ""


def extract_text_with_local_fallbacks(image_path: str) -> str:
    text = extract_text_with_tesseract(image_path)
    if text.strip():
        return text
    return extract_text_with_easyocr(image_path)


def extract_text_from_image_vision(image_path: str) -> str:
    """Extract raw text from a single image using Google Vision OCR with graceful fallback."""
    # Prefer the REST API-key path when GOOGLE_VISION_API_KEY is set. An API key
    # works even when the org blocks service-account keys; returns None on
    # miss/error so we fall through to the client library then local OCR.
    api_text = ocr_image_with_api_key(image_path)
    if api_text and api_text.strip():
        return api_text
    try:
        with io.open(image_path, "rb") as image_file:
            content = image_file.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        if response.error.message:
            raise RuntimeError(response.error.message)

        texts = response.text_annotations
        if texts:
            return texts[0].description
        return extract_text_with_local_fallbacks(image_path)
    except Exception as exc:
        print(f"Warning: Google Vision OCR failed for {image_path}: {exc}. Falling back to local OCR.")
        return extract_text_with_local_fallbacks(image_path)

def extract_text_from_images_vision(image_paths: List[str]) -> List[str]:
    """Run OCR over multiple images and return list of page texts (in order)."""
    results = []
    for p in image_paths:
        try:
            results.append(extract_text_from_image_vision(p))
        except Exception as e:
            results.append("")  # keep alignment even on failure
            print(f"Warning: OCR failed for {p}: {e}")
    return results

def process_multiple_images_and_merge(image_paths: List[str]) -> Dict[str, Any]:
    """
    1) Run OCR on all images
    2) Merge text from all images and extract fields
    """
    pages_text = extract_text_from_images_vision(image_paths)

    # merged text = join pages with newline
    merged_text = "\n\n".join(pages_text)
    merged_fields = extract_vehicle_details_from_text(merged_text)
    return merged_fields

def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def try_parse_date(text: str) -> str | None:
    """Try to parse many human date formats; return dd-mm-yyyy or None."""
    try:
        dt = dateparser.parse(text, dayfirst=True, fuzzy=True)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return None

def find_currency_amount(s: str) -> str | None:
    """Return first currency-like amount in string (no symbol returned)."""
    # allow formats like £ 1,234.56 or 1234.56 or 1,234
    m = re.search(r"[£€\$]\s*([\d,]+(?:\.\d{1,2})?)", s)
    if m:
        return m.group(1).replace(",", "")
    m = re.search(r"([\d,]+\.\d{2})\s*(?:GBP|£|EUR|€|\$)?", s)
    if m:
        return m.group(1).replace(",", "")
    m = re.search(r"([\d,]{1,}\b)\s*(?:pound|pounds|GBP)?", s, re.IGNORECASE)
    if m:
        return m.group(1).replace(",", "")
    return None

def find_nearest_value(lines: List[str], idx: int, value_type: str = "amount") -> str | None:
    """
    Given a list of lines and index of a line containing a label/keyword,
    scan the same line then following lines to find a plausible value.
    value_type: "amount" or "date" or "text"
    """
    # check same line first
    for offset in range(0, 4):  # try same line + up to 3 following lines
        if idx + offset >= len(lines):
            break
        ln = lines[idx + offset]
        if value_type == "amount":
            amt = find_currency_amount(ln)
            if amt:
                return amt
        elif value_type == "date":
            d = try_parse_date(ln)
            if d:
                return d
        else:
            # text → after colon or after keyword
            # return text after colon if present
            if ":" in ln:
                part = ln.split(":", 1)[1].strip()
                if part:
                    return part
            # otherwise return the rest of the line
            parts = ln.strip().split()
            if len(parts) > 1:
                return " ".join(parts[1:]).strip()
    return None

def process_client_vehicle(files, db: Session, ocr_service, claim_id: int, actor_id: int, tenant_id: int):
    results = []
    uploaded_files = []

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    image_paths = []
    pdf_files = []

    for file in files:
        text, stored_path, sanitized_filename = vehicle_detail_ocr_service.process_file(
            file, db, claim_id, actor_id, tenant_id,ts
        )

        uploaded_files.append({
            "file_name": sanitized_filename,
            "file_path": stored_path
        })

        # Build full path
        base_dir = _history_base_dir()
        full_path = os.path.join(base_dir, stored_path.lstrip('/'))

        ext = os.path.splitext(sanitized_filename)[1].lower()

        if ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]:
            image_paths.append(full_path)
        elif ext == ".pdf":
            pdf_files.append((text, sanitized_filename))
        else:
            pdf_files.append((text, sanitized_filename))

    # --- Step 2: Process all images together (new behavior) ---
    if image_paths:
        all_image_texts = []
        for image_path in image_paths:
            text = extract_text_from_image_vision(image_path)
            all_image_texts.append(text)

        merged_text = "\n\n".join(all_image_texts)
        consolidated_result = extract_vehicle_details_from_text(merged_text)
        results.append(consolidated_result)

    # --- Step 3: Process PDFs individually (old behavior) ---
    for raw_text, filename in pdf_files:
        parsed = extract_vehicle_details_from_text(
            raw_text if isinstance(raw_text, str) else ""
        )
        results.append(parsed)

    return results, uploaded_files

def extract_text_from_pdf(file_path: str) -> str:
    text = ""

    # Step 1: Try standard text extraction (Fast)
    doc = fitz.open(file_path)
    for page in doc:
        text += page.get_text() + "\n"

    # Step 2: If no text (Scanned PDF) -> Use Tesseract OCR
    if len(text.strip()) < 20:
        ocr_text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Render page to a high-resolution image (300 DPI)
            # Matrix(2, 2) scales the image by 2x for better OCR accuracy
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            
            # Convert Pixmap to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            # Prefer Google Vision (reliable in prod) for the rendered page; it
            # falls back to Tesseract internally and returns "" on failure, so an
            # OCR-engine error can never abort the whole import.
            page_ocr = ""
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _tmp:
                    _tmp.write(img_data)
                    _tmp_path = _tmp.name
                try:
                    page_ocr = extract_text_from_image_vision(_tmp_path)
                finally:
                    try:
                        os.remove(_tmp_path)
                    except OSError:
                        pass
            except Exception as _exc:  # pylint: disable=broad-exception-caught
                print(f"Warning: scanned-PDF OCR failed on page {page_num + 1}: {_exc}")
            ocr_text += f"--- Page {page_num + 1} ---\n{page_ocr}\n"
            
        doc.close()
        return ocr_text

    doc.close()
    return text

def extract_vehicle_details_from_text(full_text: str):
    """
    Improved extractor that:
      - Uses lookahead in regexes to avoid grabbing following section tokens,
      - Cleans trailing single-letter OCR artifacts,
      - Uses a color whitelist fallback for better color extraction.
    """
    fields = {
        "make": "",
        "model": "",
        "body_type": "",
        "registration": "",
        "color": "",
        "engine_size": "",
        "fuel_type_id": None,
        "transmission_id": None,
        "number_of_seat": "",
        "vehicle_category": "",
    }

    if not full_text or not full_text.strip():
        return fields

    # Normalize
    single_line = re.sub(r"\s+", " ", full_text).strip()
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    lines = [re.sub(r"\s+", " ", l) for l in lines]

    # lookahead tokens commonly present after fields (stop capture before these)
    stop_tokens = r"(?:\bD\.2\b|\bD2\b|\bD\.3\b|\bD\.4\b|\bD\.5\b|\bModel\b|\bType\b|\bColour\b|\bColor\b|\bBody\b|\bP\.1\b|\bS\.1\b|\bV\.7\b|\bJ\b|\bP\.1\b|\b$)"

    patterns = {
        # Capture minimal run of chars, stop at common next-field markers using lookahead
        "make": [
            rf"D\.1[:\s]*Make\s*[:\-]?\s*([A-Za-z0-9\- ]+?)(?=\s{stop_tokens})",
            rf"\bMake\s*[:\-]?\s*([A-Za-z0-9\- ]+?)(?=\s{stop_tokens})",
            r"(?:D\.?1|0\.?1|O\.?1)[:;\s]*(?:Make|Mee|Mke)?\s*([A-Z][A-Z0-9\- ]{1,30})",
        ],
        "model": [
            rf"D\.3[:\s]*Model\s*[:\-]?\s*([A-Za-z0-9 \-]+?)(?=\s{stop_tokens})",
            rf"\bModel\s*[:\-]?\s*([A-Za-z0-9 \-]+?)(?=\s{stop_tokens})",
            rf"D\.\d[:\s]*Type\s*[:\-]?\s*([A-Za-z0-9 \-]+?)(?=\s{stop_tokens})",
            r"(?:D\.?3|D\.?2|0\.?2|O\.?2)[:;\s]*(?:Model|Mode|Type|Tye|te)?\s*([A-Z0-9][A-Z0-9 \-]+?)(?=\s+(?:O\.|0\.|D\.|X\)|P[\.23]|6\.1|S\.1|Body|Tax|$))",
        ],
        "body_type": [r"Body\s*Type\s*[:\-]?\s*([A-Za-z0-9 ]+)",
                      r"Body\s*[:\-]?\s*([A-Za-z0-9 ]+)",
                      r"Body\s*(?:type|tye|tre|te)\s*[:\-]?\s*([A-Za-z0-9 ]+?)(?=\s+(?:O\.|0\.|D\.|X\)|P|6\.1|S\.1|Tax|$))",
        ],
        "registration": [
            r"\b([A-Z]{2}\d{2}\s?[A-Z]{3})\b",
            r"\b([A-Z]{1,2}\d{1,2}\s?[A-Z]{3})\b",
        ],
        "color": [
            rf"R[:\s]*Colour\s*[:\-]?\s*([A-Za-z]+)(?=\s|$)",
            rf"\bColour\s*[:\-]?\s*([A-Za-z]+)(?=\s|$)",
            rf"\bColor\s*[:\-]?\s*([A-Za-z]+)(?=\s|$)",
            rf"\bCom(?:er|our|or)?\s*[:\-]?\s*([A-Za-z]+)(?=\s|$)",
        ],
        "engine_size": [
            r"Engine\s*Size\s*[:\-]?\s*([\d\.]+\s?[Cc][Cc]?)",
            r"Engine\s*[:\-]?\s*([\d\.]+\s?L)",
            r"Cylinder capacity\s*[:\-]?\s*([\d,]+\s?CC|\d+\s?CC|\d+\s?cc)",
            r"P\.1[:\s]*Cylinder capacity\s*\(?cc\)?\s*[:\-]?\s*([\d,]+\s?CC|\d+\s?CC)",
            r"Cy(?:l|i)nder.{0,30}?([0-9]{3,5}\s?CC)",
        ],
        "number_of_seat": [
            r"No\.?\s*of\s*seats?\s*[:\-]?\s*(\d{1,2})",
            r"Number of seats[:,]?\s*(\d{1,2})",
            r"S\.1[:\s]*Number of seats[,]?\s*(\d{1,2})",
            r"(?:S\.?1|6\.?1)[:\s]*.*?seats?[,.\s]*(\d{1,2})",
        ],
        "vehicle_category": [
            r"Vehicle category\s*[:\-]?\s*([A-Za-z0-9]+)",
            r"\bJ[:\s]*Vehicle category\s*[:\-]?\s*([A-Za-z0-9]+)",
            r"\bJ[:\s]*([A-Za-z0-9]+)\b",
        ],
    }

    for field, pats in patterns.items():
        for pat in pats:
            try:
                m = re.search(pat, single_line, re.IGNORECASE)
            except re.error:
                m = None
            if m:
                fields[field] = m.group(1).strip()
                break

    keyword_map = {
        "make": ["make", "d.1"],
        "model": ["model", "type", "d.3", "d.2", "d.3:"],
        "body_type": ["body type", "body"],
        "registration": ["registration", "registration number", "reg"],
        "color": ["colour", "color", "r colour", "r: colour"],
        "engine_size": ["engine size", "cylinder capacity", "p.1"],
        "number_of_seat": ["no. of seats", "number of seats", "s.1", "seats"],
        "vehicle_category": ["vehicle category", "j:"],
    }

    for idx, line in enumerate(lines):
        low = line.lower()
        for field, keywords in keyword_map.items():
            if fields[field]:
                continue
            if any(k in low for k in keywords):
                # prefer text after colon if it exists
                if ":" in line:
                    val = line.split(":", 1)[1].strip()
                else:
                    # naive fallback: take remainder after keyword
                    parts = re.split(r"\b(?:%s)\b" % "|".join(re.escape(k) for k in keywords), line, flags=re.IGNORECASE)
                    val = parts[-1].strip() if parts and len(parts) > 0 else ""
                # remove trailing labels like "ESTATE" may appear on next line; keep as-is for now
                fields[field] = val
                break

    fuel_map = {
        "petrol": 1,
        "diesel": 2,
        "electric": 3,
        "hybrid": 3,
        "hybrid elec": 3,
        "hybrid electric": 3,
    }

    sl = single_line.lower()
    for fname, fid in fuel_map.items():
        if fname in sl:
            fields["fuel_type_id"] = fid
            break

    transmission_map = {"manual": 2, "automatic": 1, "auto": 1}
    for tname, tid in transmission_map.items():
        if tname in sl:
            fields["transmission_id"] = tid
            break

    def strip_trailing_single_char_token(s: str) -> str:
        if not s:
            return s
        s = s.strip()
        s = s.rstrip(" .,:;-")
        tokens = s.split()
        if len(tokens) >= 2 and len(tokens[-1]) == 1 and re.fullmatch(r"[A-Z]", tokens[-1], re.IGNORECASE):
            tokens = tokens[:-1]
            s = " ".join(tokens)
        s = re.sub(r"([A-Za-z0-9])[^A-Za-z0-9]+$", r"\1", s)
        return s.strip()

    for k in ("make", "model", "color"):
        fields[k] = strip_trailing_single_char_token(fields.get(k, "") or "")

    common_makes = [
        "TOYOTA", "FORD", "VAUXHALL", "VOLKSWAGEN", "BMW", "MERCEDES", "AUDI",
        "NISSAN", "HONDA", "HYUNDAI", "KIA", "PEUGEOT", "RENAULT", "SKODA",
        "SEAT", "VOLVO", "TESLA", "LEXUS", "LAND ROVER", "RANGE ROVER",
    ]
    make_source = f"{fields.get('make', '')} {single_line}".upper()
    for make in common_makes:
        if re.search(r"\b" + re.escape(make) + r"\b", make_source):
            fields["make"] = make.title()
            break

    fields["model"] = (
        fields["model"]
        .replace("HYBAD", "HYBRID")
        .replace("HYBRD", "HYBRID")
        .replace("VVT4", "VVT-I")
        .replace("CvT", "CVT")
    )

    common_body_types = [
        "ESTATE", "HATCHBACK", "SALOON", "COUPE", "CONVERTIBLE", "MPV", "SUV",
        "PICKUP", "VAN", "MINIBUS",
    ]
    body_source = f"{fields.get('body_type', '')} {single_line}".upper()
    for body_type in common_body_types:
        if re.search(r"\b" + re.escape(body_type) + r"\b", body_source):
            fields["body_type"] = body_type
            break

    if fields["vehicle_category"].upper() in {"MI", "M L", "M I"}:
        fields["vehicle_category"] = "M1"

    if not fields["transmission_id"] and re.search(r"\b(?:automated|automatic|tometed|artometes|atmce)\b", single_line, re.IGNORECASE):
        fields["transmission_id"] = 1

    # If the captured colour is empty OR not an actual vehicle colour (the generic
    # capture can latch onto a nearby "Technical"/heading word on the V5C), fall
    # back to the first real colour word found anywhere in the document text.
    common_colors = [
        "WHITE","BLACK","SILVER","GREY","GRAY","BLUE","RED","GREEN","YELLOW",
        "BEIGE","BROWN","GOLD","BRONZE","MAROON","PURPLE","PINK","ORANGE",
        "CREAM","NAVY","TURQUOISE","MULTICOLOUR","MULTICOLOR",
    ]
    _valid = {c.lower() for c in common_colors}
    if not fields["color"] or fields["color"].strip().lower() not in _valid:
        matched = ""
        for col in common_colors:
            if re.search(r"\b" + re.escape(col.lower()) + r"\b", single_line.lower()):
                matched = col.title()
                break
        # Use the real colour if found; otherwise clear the junk value.
        fields["color"] = matched

    fields["color"] = strip_trailing_single_char_token(fields["color"])

    if fields["registration"]:
        fields["registration"] = re.sub(r"\s+", "", fields["registration"]).upper()

    for k, v in list(fields.items()):
        if isinstance(v, str):
            fields[k] = v.strip()

    return fields

class VehicleOCRService:
    def process_file(
        self,
        file,
        db: Session,
        claim_id: int,
        actor_id: int,
        tenant_id: int,
        ts: str
    ):
        # Validate claim exists
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise ValueError(f"Claim with id {claim_id} does not exist")

        base_dir = _history_base_dir()
        target_dir = os.path.join(base_dir, str(claim_id), ts)
        os.makedirs(target_dir, exist_ok=True)

        # Sanitize filename
        original_filename = file.filename or "file.bin"
        safe_filename = original_filename.replace("/", "_").replace("..", "_")
        sanitized_filename = urllib.parse.quote(safe_filename)
        display_filename = safe_filename

        full_path = os.path.join(target_dir, sanitized_filename)

        # Read file once
        file_bytes = file.file.read()

        # Save locally, keeping your existing OCR flow
        with open(full_path, "wb") as f:
            f.write(file_bytes)

        ext = os.path.splitext(safe_filename)[1].lower() or ".bin"
        content_type = (
            getattr(file, "content_type", None)
            or mimetypes.guess_type(safe_filename)[0]
            or "application/octet-stream"
        )

        # Extract text, same as your existing function
        text = ""
        if ext == ".pdf":
            text = extract_text_from_pdf(full_path)
        elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]:
            text = extract_text_from_image_vision(full_path)
        else:
            text = ""

        # Relative local path for old functionality
        rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
        stored_path = "/" + rel_path

        reference = build_case_reference(claim_id, db)

        # Upload same file to S3
        s3_service = S3Service()

        upload_result = s3_service.upload_claim_document_bytes_with_fallback(
            file_bytes=file_bytes,
            claim_id=claim_id,
            filename=safe_filename,
            folder="uploads",
            content_type=content_type,
            fallback_local_path=full_path,
        )

        s3_key = upload_result.get("s3_key", "")
        file_url = upload_result.get("file_url", "")
        storage_backend = upload_result.get("storage_backend", "s3")
        storage_error = upload_result.get("storage_error")

        stored_s3_filename = s3_key.split("/")[-1] if s3_key else sanitized_filename

        # Store in case_documents, same pattern as witness
        case_document = CaseDocument(
            claim_id=claim_id,
            file_name=stored_s3_filename,
            original_filename=safe_filename,
            file_extension=ext,
            content_type=content_type,
            file_size_bytes=len(file_bytes),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            category="Claim Entrance Documents",
            tag="vehicle_detail",
            source_type="history_upload",
            s3_key=s3_key,
            file_url=file_url,
            version=1,
            is_latest=True,
            is_active=True,
            is_deleted=False,
            tenant_id=tenant_id,
            created_by=actor_id,
            updated_by=actor_id,
            metadata_json={
                "claim_id": claim_id,
                "case_reference": reference,
                "original_filename": safe_filename,
                "local_path": stored_path,
                "document_role": "uploaded_file",
                "preview_type": "pdf" if ext == ".pdf" else "image" if ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"] else "file",
                "storage_backend": storage_backend,
                "storage_error": storage_error,
            },
        )

        db.add(case_document)
        db.flush()
        db.refresh(case_document)

        # Store in history_activities, same style as witness payload
        activity_payload = {
            "source_type": "history_upload",
            "title": "File Uploaded",
            "summary": f'The file "{display_filename}" has been uploaded successfully.',
            "file_name": safe_filename,
            "file_url": file_url,
            "s3_key": s3_key,
            "case_document_id": case_document.id,
            "local_path": stored_path,
            "content_type": content_type,
            "file_extension": ext,
            "storage_backend": storage_backend,
        }

        history = HistoryActivities(
            claim_id=claim_id,
            file_name=f'The file named "{display_filename}" has been saved for claim {reference}',
            file_path=json.dumps(activity_payload),
            file_type=HistoryLogType.HISTORYUPLOAD,
            created_by=actor_id,
            updated_by=actor_id,
            tenant_id=tenant_id,
        )

        db.add(history)
        db.flush()
        db.refresh(history)

        # Commit here because your old commented history code also committed inside this method
        db.commit()

        return text, stored_path, sanitized_filename
vehicle_detail_ocr_service = VehicleOCRService()
