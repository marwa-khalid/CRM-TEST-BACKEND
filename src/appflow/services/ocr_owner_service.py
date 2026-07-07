# libocr/ocr_owner_service.py
import os
import re
import urllib.parse
from PIL import Image
import numpy as np
from io import BytesIO
from pdf2image import convert_from_path
from datetime import datetime
from libdata.enums import HistoryLogType
from libdata.models.tables import HistoryActivities, Claim
from sqlalchemy.orm import Session


_easyocr_reader = None


def get_easyocr_reader():
    """Initialise EasyOCR only when an owner OCR upload actually needs it."""
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(["en"])
    return _easyocr_reader


UPLOAD_DIR = "uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

POPPLER_PATH = os.environ.get("POPPLER_PATH")
if not POPPLER_PATH and os.path.exists("/usr/bin/pdfinfo"):
    POPPLER_PATH = "/usr/bin"


def extract_text_from_owner_file(file_path: str) -> str:
    """
    Extract raw text from owner document (PDF/image).
    """
    text = ""
    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext == ".pdf":
        convert_kwargs = {}
        if POPPLER_PATH:
            convert_kwargs["poppler_path"] = POPPLER_PATH
        images = convert_from_path(file_path, **convert_kwargs)
        for page in images:
            img = BytesIO()
            page.save(img, format="PNG")
            img.seek(0)
            img_np = np.array(Image.open(img))
            ocr_result = get_easyocr_reader().readtext(img_np)
            for _, txt, _ in ocr_result:
                text += txt + "\n"

    elif file_ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]:
        img_np = np.array(Image.open(file_path))
        ocr_result = get_easyocr_reader().readtext(img_np)
        for _, txt, _ in ocr_result:
            text += txt + "\n"

    return text


def parse_owner_details(text: str) -> dict:
    """
    Parse structured owner details (name, address, postcode, etc.) from OCR text.
    """

    # Extract postcode (UK-style)
    postcode_match = re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", text)
    postcode = postcode_match.group(0) if postcode_match else ""

    # Extract possible name
    name_match = re.search(r"(Mr|Mrs|Miss|Ms|Dr)\s+([A-Z][a-zA-Z]+)(?:\s+([A-Z][a-zA-Z]+))?", text)
    first_name = name_match.group(2) if name_match else ""
    surname = name_match.group(3) if name_match and name_match.lastindex >= 3 else ""

    # Extract address → take a few lines before postcode
    address = ""
    if postcode:
        before_postcode = text.split(postcode)[0]
        lines = before_postcode.strip().split("\n")
        address = " ".join(lines[-3:])  # last 3 lines before postcode

    # Payment beneficiary (look for keyword)
    payment_match = re.search(r"Official|Beneficiary|Owner", text, re.IGNORECASE)
    payment_beneficiary = payment_match.group(0) if payment_match else ""

    return {
        "first_name": first_name,
        "surname": surname,
        "address": address.strip(),
        "postcode": postcode,
        "payment_beneficiary": payment_beneficiary,
    }

def _history_base_dir():
    return os.path.abspath(os.path.join(os.getcwd(), "uploads", "history"))

class OwnerOCRService:
    def process_file(self, file,db:Session, claim_id: int, actor_id:int):
        # Validate claim exists
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise ValueError(f"Claim with id {claim_id} does not exist")

        base_dir = _history_base_dir()
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        target_dir = os.path.join(base_dir, str(claim_id), ts)
        os.makedirs(target_dir, exist_ok=True)

        # sanitize filename
        filename = file.filename or "file.bin"
        safe_filename = filename.replace("/", "_").replace("..", "_")
        sanitized_filename = urllib.parse.quote(safe_filename)
        full_path = os.path.join(target_dir, sanitized_filename)

        # Save file
        with open(full_path, "wb") as f:
            f.write(file.file.read())

        # Extract OCR text
        extracted_data = extract_text_from_owner_file(full_path)

        # Relative path for DB
        rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
        stored_path = "/" + rel_path

        # Save history record
        history = HistoryActivities(
            claim_id=claim_id,
            file_name=sanitized_filename,
            file_path=stored_path,
            file_type=HistoryLogType.VEHICLE_OWNER,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        return extracted_data, stored_path, sanitized_filename


owner_ocr_service = OwnerOCRService()
