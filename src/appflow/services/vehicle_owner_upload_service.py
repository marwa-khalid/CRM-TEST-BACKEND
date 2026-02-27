import os
import urllib.parse
import fitz  # PyMuPDF
from PIL import Image
from sqlalchemy.orm import Session
from datetime import datetime
from libdata.enums import HistoryLogType
from libdata.models.tables import HistoryActivities, Claim
from appflow.utils import build_case_reference
import io
import re
from typing import List, Dict, Any
from google.cloud import vision
from dateutil import parser as dateparser
import tempfile
import pytesseract

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(__file__), "google_credentials", "vision-service-account.json"
)

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
    """Extract raw text from a single image using Google Vision OCR."""
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

    # 1. Find postcode
    postcode = None
    postcode_index = -1
    for i, line in enumerate(lines):
        match = re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", line, re.IGNORECASE)
        if match:
            postcode = match.group(0).upper()
            postcode_index = i
            break
    fields["postcode"] = postcode if postcode else ""

    # 2. Find company/owner name
    owner_line = None
    for line in lines:
        if re.search(r"(LTD|LIMITED|PLC|LLP)", line, re.IGNORECASE):
            owner_line = line.title()
            break

    if owner_line:
        name_parts = owner_line.split(" ", 1)
        fields["first_name"] = name_parts[0]
        fields["surname"] = name_parts[1] if len(name_parts) > 1 else ""
        fields["payment_benificiary"] = owner_line

    # 3. Collect address: continuous block just before postcode
    address_lines = []
    if postcode and postcode_index > 0:
        for j in range(postcode_index - 1, -1, -1):  # walk upwards
            line = lines[j]
            # Stop if line looks like a date or a sentence
            if re.search(r"\d{1,2}\s?\d{1,2}\s?\d{2,4}", line):  # date
                break
            if len(line.split()) > 6:  # too many words → likely a sentence
                break
            address_lines.insert(0, line)  # prepend

    # Clean address: join lines into one, remove extra spaces
    clean_address = " ".join(address_lines)
    clean_address = re.sub(r"\s{2,}", " ", clean_address).strip()

    fields["address"] = clean_address

    return fields



def extract_text_from_pdf(file_path: str) -> str:
    import fitz
    from pdf2image import convert_from_path

    text = ""

    # Step 1: Try PyMuPDF
    pdf = fitz.open(file_path)
    for page_num in range(pdf.page_count):
        page = pdf.load_page(page_num)
        text += page.get_text("text") + "\n"

    # Step 2: If no text → OCR fallback
    if len(text.strip()) < 20:
        convert_kwargs = {"dpi": 300}
        if POPPLER_PATH:
            convert_kwargs["poppler_path"] = POPPLER_PATH
        try:
            images = convert_from_path(file_path, **convert_kwargs)
        except Exception as e:
            # If poppler is not available, return the text extracted by PyMuPDF
            # even if it's minimal, rather than failing completely
            if "poppler" in str(e).lower() or "page count" in str(e).lower():
                raise Exception(
                    "Poppler is required for PDF OCR processing. "
                    "Please install poppler-utils (e.g., 'apt-get install poppler-utils' on Ubuntu) "
                    "or set POPPLER_PATH environment variable."
                ) from e
            raise
        ocr_text = ""

        for i, img in enumerate(images):
            # FIX: Windows-safe temp file handling
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()

            img.save(tmp_path, format="PNG")
            page_ocr = extract_text_from_image_vision(tmp_path)
            ocr_text += page_ocr + "\n"

            os.remove(tmp_path)

        return ocr_text

    return text


class VehicleOCRService:
    def process_file(self, file, db: Session, claim_id: int, actor_id: int,tenant_id:int,ts:str):
        # Validate claim exists
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise ValueError(f"Claim with id {claim_id} does not exist")

        base_dir = _history_base_dir()
        # ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        target_dir = os.path.join(base_dir, str(claim_id), ts)
        os.makedirs(target_dir, exist_ok=True)

        # sanitize filename
        filename = file.filename or "file.bin"
        safe_filename = filename.replace("/", "_").replace("..", "_")
        sanitized_filename = urllib.parse.quote(safe_filename)
        display_filename = safe_filename
        full_path = os.path.join(target_dir, sanitized_filename)

        # save file
        with open(full_path, "wb") as f:
            f.write(file.file.read())

        # extract text
        ext = os.path.splitext(full_path)[1].lower()
        text = ""
        if ext == ".pdf":
            text = extract_text_from_pdf(full_path)
        elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]:
            text = extract_text_from_image_vision(full_path)
            # pdf_path = convert_image_to_pdf(full_path)
        else:
            text = ""

        # relative path for response/database
        rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
        stored_path = "/" + rel_path

        reference = build_case_reference(claim_id,db)
        # save history activity
        history = HistoryActivities(
            claim_id=claim_id,
            file_name=f'The file named "{display_filename}" has been saved for claim {reference}',
            file_path=stored_path,
            file_type=HistoryLogType.ENGINEER_DETAIL,
            created_by=actor_id,
            updated_by=actor_id,
            tenant_id=tenant_id,
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        return text, stored_path, sanitized_filename

vehicle_ocr_service = VehicleOCRService()
