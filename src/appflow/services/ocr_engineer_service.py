import os
import urllib.parse
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from sqlalchemy.orm import Session
from appflow.services.engineer_detail_service import EngineerDetailService
from libdata.enums import HistoryLogType
from datetime import datetime, timezone
from libdata.models.tables import HistoryActivities, Claim, CaseDocument
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
from appflow.services.google_vision_auth import configure_google_vision_credentials

configure_google_vision_credentials()
client = vision.ImageAnnotatorClient()

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
    """Fallback OCR using local Tesseract when Google Vision is unavailable."""
    try:
        with Image.open(image_path) as img:
            return pytesseract.image_to_string(img)
    except Exception as exc:
        print(f"Warning: Local OCR failed for {image_path}: {exc}")
        return ""


def extract_text_from_image_vision(image_path: str) -> str:
    """Extract raw text from a single image using Google Vision OCR with graceful fallback."""
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
        return ""
    except Exception as exc:
        print(f"Warning: Google Vision OCR failed for {image_path}: {exc}. Falling back to Tesseract.")
        return extract_text_with_tesseract(image_path)
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
    merged_fields = extract_engineer_data_from_text(merged_text)
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

def extract_engineer_data_from_text(full_text: str) -> Dict[str, Any]:
    """
    Extract fields from *all pages merged* text. Also uses line scanning fallback.
    """
    # prepare fields
    fields = {
        "engineer_instructed": "",
        "inspection_date": "",
        "engineer_report_received_date": "",
        "engineer_fee": "",
        "labour": "",
        "paint_material": "",
        "parts": "",
        "miscellaneous": "",
        "job_hire": "",
        "sub_total": "",
        "vat": "",
        "total_inc_vat": "",
        "pav": "",
        "salvage_amount": "",
        "salvage_category": "",
    }

    if not full_text or not full_text.strip():
        return fields

    # Normalize for regex scanning (single-line)
    single_line = collapse_whitespace(full_text)

    # Patterns (more forgiving)
    patterns = {
        "engineer_instructed": [
            r"Date\s*(?:of\s*)?Instructed\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
            r"Instructed\s*[:\-]\s*([\d]{1,2}\s+\w+\s+\d{4})",
        ],
        "inspection_date": [
            r"Date\s*(?:of\s*)?Inspection\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
            r"Inspection\s*Date\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
        ],
        "engineer_report_received_date": [
            r"Date\s*(?:of\s*)?Report\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
            r"Report\s*Date\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
        ],
        "engineer_fee": [
            r"Engineers?\.?\s*Report\s*Fee\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})",
            r"Engineers?\.?\s*Fee\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})",
            r"Invoice\s*/\s*Fee\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})",
        ],
        "labour": [r"Labour\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})", r"Labour\s*£\s*([\d,]+\.\d{2})"],
        "paint_material": [r"Paint\s*(?:\/|\s)?Materials?\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})"],
        "parts": [r"Parts\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})"],
        "miscellaneous": [r"Specialist\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})", r"Specialist\s*Charge\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})"],
        "sub_total": [r"Total\s*Exc(?:lude)?\s*VAT\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})", r"Total\s*Exc\s*VAT\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})"],
        # "vat": [r"VAT\s*@?\s*\d{1,3}%?\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})"],
        "vat": [
            r"V\.?A\.?T\.?\s*@?\s*\d{1,3}%?\s*[£€$\ε]?\s*([\d,]+\.\d{2})",
            r"VAT\s*@?\s*\d{1,3}%?\s*[£€$\ε]?\s*([\d,]+\.\d{2})",
        ],
        "total_inc_vat": [r"Total\s*Inc\s*VAT\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})", r"Total\s*Including\s*VAT\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})"],
        "pav": [r"Engineers?\s*(?:Valuation\s*Figure|Valuation)\s*[:\-]?\s*[£€$]?\s*([\d,]+\.\d{2})"],
        "salvage_amount": [r"Salvage\s*Value\s*[:\-]?\s*[£€$]?\s*([\d,]+(?:\.\d{1,2})?)"],
        "salvage_category": [r"Motor\s*Salvage\s*Category\s*[:\-]?\s*([A-Z])"],
    }

    # First pass: single-line regexes
    for field, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, single_line, re.IGNORECASE)
            if m:
                val = m.group(1).replace(",", "").replace("£", "").replace("€", "").strip()
                # dates -> normalize
                if field in {"engineer_instructed", "inspection_date", "engineer_report_received_date"}:
                    parsed = try_parse_date(val)
                    fields[field] = parsed or val
                else:
                    fields[field] = val
                break

    # If some fields still empty, try line-by-line scanning (fallback)
    if any(v == "" for v in fields.values()):
        lines = [l.strip() for l in re.split(r"[\r\n]+", full_text) if l.strip()]
        # collapse multiple spaces in each line
        lines = [re.sub(r"\s+", " ", l) for l in lines]

        # keyword maps: label -> (field name, value type)
        keywords = {
            "date instructed": ("engineer_instructed", "date"),
            "date of inspection": ("inspection_date", "date"),
            "date of report": ("engineer_report_received_date", "date"),
            "engineer report fee": ("engineer_fee", "amount"),
            "engineers report fee": ("engineer_fee", "amount"),
            "engineer fee": ("engineer_fee", "amount"),
            "labour": ("labour", "amount"),
            "paint materials": ("paint_material", "amount"),
            "paint / materials": ("paint_material", "amount"),
            "parts": ("parts", "amount"),
            "specialist": ("miscellaneous", "amount"),
            "total exc vat": ("sub_total", "amount"),
            "total inc vat": ("total_inc_vat", "amount"),
            "vat": ("vat", "amount"),
            "engineers valuation figure": ("pav", "amount"),
            "salvage value": ("salvage_amount", "amount"),
            "motor salvage category": ("salvage_category", "text"),
        }

        for idx, line in enumerate(lines):
            low = line.lower()
            for k, (field, vtype) in keywords.items():
                if field in fields and fields[field]:  # skip if already found
                    continue
                if k in low:
                    val = find_nearest_value(lines, idx, value_type=vtype)
                    if val:
                        if vtype == "date":
                            parsed = try_parse_date(val)
                            fields[field] = parsed or val
                        elif vtype == "amount":
                            fields[field] = val.replace(",", "").replace("£", "").replace("€", "")
                        else:
                            fields[field] = val.strip()

    # Final normalization: ensure numbers are simple strings
    for k in ["labour", "paint_material", "parts", "miscellaneous", "sub_total", "vat", "total_inc_vat", "pav", "salvage_amount", "engineer_fee"]:
        if fields.get(k):
            fields[k] = fields[k].replace("£", "").replace(",", "").strip()

    # salvage_category should be single letter uppercase if present
    if fields.get("salvage_category"):
        fields["salvage_category"] = fields["salvage_category"].strip().upper()[:1]

    return fields

def process_engineer_detail(files, db: Session, ocr_service, claim_id: int, actor_id: int, tenant_id: int):
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
        consolidated_result = extract_engineer_data_from_text(merged_text)
        results.append(consolidated_result)

    # --- Step 3: Process PDFs individually (old behavior) ---
    for raw_text, filename in pdf_files:
        parsed = EngineerDetailService.extract_engineer_data(
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
            
            # Use Pytesseract to extract text
            page_ocr = pytesseract.image_to_string(img)
            ocr_text += f"--- Page {page_num + 1} ---\n{page_ocr}\n"
            
        doc.close()
        return ocr_text

    doc.close()
    return text


def convert_image_to_pdf(image_path: str) -> str:
    """Convert image to a temporary PDF file for unified parsing."""
    img = Image.open(image_path)
    pdf_path = image_path + ".pdf"
    img.convert("RGB").save(pdf_path)
    return pdf_path


class EngineerOCRService:
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
            category="engineer-detail",
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
            tag="engineer-detail",
            source_type="engineer_detail_upload",
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
                "document_role": "engineer_detail_upload",
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
            "source_type": "engineer_detail_upload",
            "title": "Engineer Detail File Uploaded",
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
            file_type=HistoryLogType.ENGINEER_DETAIL,
            created_by=actor_id,
            updated_by=actor_id,
            tenant_id=tenant_id,
        )

        db.add(history)
        db.flush()
        db.refresh(history)

        db.commit()

        return text, stored_path, sanitized_filename
engineer_ocr_service = EngineerOCRService()
