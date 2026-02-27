import os
import urllib.parse
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
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
from pdf2image import convert_from_path
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
        ],
        "model": [
            rf"D\.3[:\s]*Model\s*[:\-]?\s*([A-Za-z0-9 \-]+?)(?=\s{stop_tokens})",
            rf"\bModel\s*[:\-]?\s*([A-Za-z0-9 \-]+?)(?=\s{stop_tokens})",
            rf"D\.\d[:\s]*Type\s*[:\-]?\s*([A-Za-z0-9 \-]+?)(?=\s{stop_tokens})",
        ],
        "body_type": [r"Body\s*Type\s*[:\-]?\s*([A-Za-z0-9 ]+)",
                      r"Body\s*[:\-]?\s*([A-Za-z0-9 ]+)",
        ],
        "registration": [
            r"\b([A-Z]{1,2}\d{1,2}\s?[A-Z]{3})\b",
        ],
        "color": [
            rf"R[:\s]*Colour\s*[:\-]?\s*([A-Za-z]+)(?=\s|$)",
            rf"\bColour\s*[:\-]?\s*([A-Za-z]+)(?=\s|$)",
            rf"\bColor\s*[:\-]?\s*([A-Za-z]+)(?=\s|$)",
        ],
        "engine_size": [
            r"Engine\s*Size\s*[:\-]?\s*([\d\.]+\s?[Cc][Cc]?)",
            r"Engine\s*[:\-]?\s*([\d\.]+\s?L)",
            r"Cylinder capacity\s*[:\-]?\s*([\d,]+\s?CC|\d+\s?CC|\d+\s?cc)",
            r"P\.1[:\s]*Cylinder capacity\s*\(?cc\)?\s*[:\-]?\s*([\d,]+\s?CC|\d+\s?CC)",
        ],
        "number_of_seat": [
            r"No\.?\s*of\s*seats?\s*[:\-]?\s*(\d{1,2})",
            r"Number of seats[:,]?\s*(\d{1,2})",
            r"S\.1[:\s]*Number of seats[,]?\s*(\d{1,2})",
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

    if not fields["color"]:
        common_colors = [
            "WHITE","BLACK","SILVER","GREY","GRAY","BLUE","RED","GREEN","YELLOW",
            "BEIGE","BROWN","GOLD","BRONZE","MAROON","PURPLE","PINK","ORANGE"
        ]
        for col in common_colors:
            if re.search(r"\b" + re.escape(col.lower()) + r"\b", single_line.lower()):
                fields["color"] = col.title()
                break

    fields["color"] = strip_trailing_single_char_token(fields["color"])

    if fields["registration"]:
        fields["registration"] = re.sub(r"\s+", "", fields["registration"]).upper()

    for k, v in list(fields.items()):
        if isinstance(v, str):
            fields[k] = v.strip()

    return fields

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

vehicle_detail_ocr_service = VehicleOCRService()
