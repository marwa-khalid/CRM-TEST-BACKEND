import os
import urllib.parse
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageOps
import numpy as np
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from libdata.models.tables import HistoryActivities, Claim, CaseDocument
from libdata.enums import HistoryLogType
from appflow.services.s3_service import S3Service
import json
from libdata.models.tables import HistoryActivities, Claim
from appflow.utils import build_case_reference
import io
import re
from typing import List, Dict, Any
from google.cloud import vision
from dateutil import parser as dateparser
import tempfile
import pytesseract
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
    """Extract raw text from a single image using Google Vision OCR."""
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
    merged_fields = extract_owner_data(merged_text)
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

def process_vehicle_owner(files, db: Session, ocr_service, claim_id: int, actor_id: int, tenant_id: int):
    results = []
    uploaded_files = []

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    image_paths = []
    pdf_files = []

    # --- Step 1: Save all files and separate image files vs PDFs ---
    for file in files:
        text, stored_path, sanitized_filename = ocr_service.process_file(
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
            # Unknown file type fallback
            pdf_files.append((text, sanitized_filename))

    # --- Step 2: Process all images together (new behavior) ---
    if image_paths:
        all_image_texts = []
        for image_path in image_paths:
            text = extract_text_from_image_vision(image_path)
            all_image_texts.append(text)

        merged_text = "\n\n".join(all_image_texts)
        consolidated_result = extract_owner_data(merged_text)
        results.append(consolidated_result)

    # --- Step 3: Process PDFs individually (old behavior) ---
    for raw_text, filename in pdf_files:
        parsed = extract_owner_data(
            raw_text if isinstance(raw_text, str) else ""
        )
        results.append(parsed)

    return results, uploaded_files

def extract_owner_data(text: str):
    fields = {
        "gender":"",
        "first_name": "",
        "surname": "",
        "address": "",
        "postcode": "",
        "payment_benificiary": "",
        "home_tel": "",
        "mobile_tel": "",
        "email": "",
    }

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return fields

    single_line = re.sub(r"\s+", " ", text).strip()

    def clean_label_noise(value: str) -> str:
        value = re.sub(r"\b(?:Registration|number|nurnber|Document reference number)\b", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"\b[A-Z]{1,2}\d{1,2}\s?[A-Z]{3}\b", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value).strip(" ,:;-")
        return value

    def normalize_postcode(value: str) -> str:
        compact = value.upper().replace(" ", "")
        match = re.search(r"([A-Z]{1,2}\d{1,2}[A-Z]?)(\d[A-Z]{2})", compact)
        if match:
            return f"{match.group(1)} {match.group(2)}"
        return ""

    # 1. Find postcode
    postcode = None
    postcode_index = -1
    for i, line in enumerate(lines):
        match = re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", line, re.IGNORECASE)
        if match:
            postcode = match.group(0).upper()
            postcode_index = i
            break
        fallback = normalize_postcode(line)
        if fallback:
            postcode = fallback
            postcode_index = i
            break
    fields["postcode"] = postcode if postcode else ""

    # 2. Registered-keeper block: the contiguous run of short, non-label lines
    # ending just above the postcode. On a V5C this reads as:
    #     NAME / <address line(s)> / POSTCODE
    # so the first name-like line is the keeper and the lines below it are the
    # address. (This section used to be hardcoded to one sample document.)
    STREET_KW = re.compile(
        r"\b(ROAD|RD|STREET|ST|LANE|LN|AVENUE|AVE|CLOSE|COURT|CT|CRESCENT|DRIVE|DR|"
        r"WAY|PLACE|PL|TERRACE|GARDENS|GROVE|WALK|HILL|PARK|SQUARE|SQ|ROW|MEWS|VIEW|"
        r"RISE|HOUSE|FLAT|APARTMENT|APT)\b",
        re.IGNORECASE,
    )
    LABEL_RE = re.compile(
        r"(REGISTER|KEEPER|DOCUMENT|REFERENCE|BUYER|BEWARE|SELLING|CONTACT|SURNAME|"
        r"FIRST\s*NAME|DVLA|SECTION|DECLARATION|SIGNATURE|SPECIAL|\bMAKE\b|\bMODEL\b)",
        re.IGNORECASE,
    )

    def looks_like_name(value: str) -> bool:
        if not value or any(ch.isdigit() for ch in value) or STREET_KW.search(value):
            return False
        return 1 <= len(value.split()) <= 4

    def strip_title(value: str):
        m = re.match(r"^\s*(MR|MRS|MISS|MS|DR)\.?\s+(.*)$", value, re.IGNORECASE)
        return (m.group(1).lower(), m.group(2).strip()) if m else ("", value)

    block = []
    if postcode and postcode_index > 0:
        for j in range(postcode_index - 1, -1, -1):
            line = lines[j]
            if re.fullmatch(r"\d[\d_]{5,}[A-Za-z]?", line):  # DVLA reference/barcode number
                break
            if LABEL_RE.search(line):
                break
            if re.search(r"\d{1,2}[/. ]\d{1,2}[/. ]\d{2,4}", line):  # a date
                break
            if len(line.split()) > 7:  # a sentence, not an address line
                break
            block.insert(0, line)
            if len(block) >= 4:  # name + up to 3 address lines
                break

    owner_name = ""
    address_lines = list(block)

    # A company keeper (LTD/LIMITED/PLC/LLP) takes precedence over a personal name.
    company_idx = None
    for k, l in enumerate(block):
        cm = re.search(r"[A-Za-z][A-Za-z0-9&.,' -]*?\s+(?:LTD|LIMITED|PLC|LLP)\b", l, re.IGNORECASE)
        if cm:
            owner_name = clean_label_noise(cm.group(0)).title()
            company_idx = k
            break
    if company_idx is not None:
        address_lines = [l for i, l in enumerate(block) if i != company_idx]
    else:
        # First name-like line in the block is the keeper; rest is the address.
        for k, cand in enumerate(block):
            gender, core = strip_title(cand)
            if looks_like_name(core):
                owner_name = core
                fields["gender"] = gender
                address_lines = block[k + 1:]
                break

    if not owner_name:
        # Fallback: a titled name anywhere in the document text.
        personal_match = re.search(
            r"\b(?:Mr|Mrs|Miss|Ms|Dr)\.?\s+([A-Z][A-Za-z'-]+)\s+([A-Z][A-Za-z'-]+)\b", text
        )
        if personal_match:
            owner_name = f"{personal_match.group(1)} {personal_match.group(2)}"
            fields["gender"] = personal_match.group(0).split()[0].lower().rstrip(".")

    if owner_name:
        name_parts = owner_name.split()
        fields["first_name"] = name_parts[0].title()
        fields["surname"] = " ".join(name_parts[1:]).title() if len(name_parts) > 1 else ""
        fields["payment_benificiary"] = owner_name.title()

    # 3. Address = the keeper-block lines below the name (up to the postcode).
    clean_address = clean_label_noise(" ".join(address_lines))
    clean_address = re.sub(r"\s{2,}", " ", clean_address).strip(" ,:;-").title()
    fields["address"] = clean_address

    return fields



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
    filename = file.filename or "file.bin"
    safe_filename = filename.replace("/", "_").replace("..", "_")
    sanitized_filename = urllib.parse.quote(safe_filename)
    display_filename = safe_filename
    full_path = os.path.join(target_dir, sanitized_filename)

    # Read file once
    file_bytes = file.file.read()

    # Save file locally for existing OCR flow
    with open(full_path, "wb") as f:
        f.write(file_bytes)

    # Extract text from local saved file
    ext = os.path.splitext(full_path)[1].lower()
    text = ""

    if ext == ".pdf":
        text = extract_text_from_pdf(full_path)
    elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]:
        text = extract_text_from_image_vision(full_path)
    else:
        text = ""

    # Relative local path for existing response/database behaviour
    rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
    stored_path = "/" + rel_path

    reference = build_case_reference(claim_id, db)

    # Upload same file to S3
    s3_service = S3Service()

    file.file.seek(0)
    upload_result = s3_service.upload_case_document_with_fallback(
        file=file,
        claim_id=claim_id,
        category="vehicle-owner",
        fallback_local_path=full_path,
    )

    s3_key = upload_result.get("s3_key", "")
    file_url = upload_result.get("file_url", "")
    storage_backend = upload_result.get("storage_backend", "s3")
    storage_error = upload_result.get("storage_error")

    stored_s3_filename = s3_key.split("/")[-1] if s3_key else sanitized_filename
    content_type = file.content_type or "application/octet-stream"

    preview_type = "file"
    if ext == ".pdf":
        preview_type = "pdf"
    elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]:
        preview_type = "image"

    # Store in case_documents
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
        tag="vehicle-owner",
        source_type="vehicle_owner_upload",
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
            "document_role": "vehicle_owner_upload",
            "preview_type": preview_type,
            "storage_backend": storage_backend,
            "storage_error": storage_error,
        },
    )

    db.add(case_document)
    db.flush()
    db.refresh(case_document)

    # Store in history_activities
    activity_payload = {
        "source_type": "vehicle_owner_upload",
        "title": "Vehicle Owner File Uploaded",
        "summary": f'The file "{display_filename}" has been uploaded for claim {reference}.',
        "file_name": safe_filename,
        "file_url": file_url,
        "s3_key": s3_key,
        "case_document_id": case_document.id,
        "local_path": stored_path,
        "content_type": content_type,
        "file_extension": ext,
        "preview_type": preview_type,
        "storage_backend": storage_backend,
    }

    history = HistoryActivities(
        claim_id=claim_id,
        file_name=f'The file named "{display_filename}" has been uploaded for claim {reference}',
        file_path=json.dumps(activity_payload),
        file_type=HistoryLogType.VEHICLE_OWNER_UPLOAD,
        created_by=actor_id,
        updated_by=actor_id,
        tenant_id=tenant_id,
    )

    db.add(history)
    db.flush()
    db.refresh(history)

    db.commit()

    return text, stored_path, sanitized_filename
vehicle_ocr_service = VehicleOCRService()
