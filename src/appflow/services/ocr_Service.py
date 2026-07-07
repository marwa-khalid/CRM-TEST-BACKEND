import os
import urllib.parse
import re
import easyocr
from PIL import Image
import numpy as np
from io import BytesIO
from pdf2image import convert_from_path
from datetime import datetime
from libdata.enums import HistoryLogType
from libdata.models.tables import HistoryActivities, Claim



# EasyOCR reader initialization
reader = easyocr.Reader(['en'])

UPLOAD_DIR = "uploads"  # Directory to store uploaded files

# Ensure the uploads directory exists
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Poppler path configuration for PDF processing
POPPLER_PATH = os.environ.get("POPPLER_PATH")
if not POPPLER_PATH and os.path.exists("/usr/bin/pdfinfo"):
    POPPLER_PATH = "/usr/bin"


def extract_text_from_file(file_path: str):
    """
    Extract text from either a PDF or image file and process it.

    Args:
        file_path (str): Path to the file to be processed

    Returns:
        dict: Extracted data after processing
    """
    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    # Get file extension to determine type
    file_ext = os.path.splitext(file_path)[1].lower()

    text = ""

    # Process PDF files
    if file_ext == '.pdf':
        # Convert PDF to images (one image per page)
        convert_kwargs = {}
        if POPPLER_PATH:
            convert_kwargs["poppler_path"] = POPPLER_PATH
        images = convert_from_path(file_path, **convert_kwargs)

        for page in images:
            img = BytesIO()
            page.save(img, format='PNG')
            img.seek(0)

            # Convert BytesIO object to a format that EasyOCR can read (NumPy array)
            img_pil = Image.open(img)
            img_np = np.array(img_pil)

            # Use EasyOCR to extract text from the image
            ocr_result = reader.readtext(img_np)
            for result in ocr_result:
                text += result[1] + "\n"

    # Process image files (common formats)
    elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
        # Open the image file directly and convert it to NumPy array
        img = Image.open(file_path)
        img_np = np.array(img)

        # Use EasyOCR to extract text from the image
        ocr_result = reader.readtext(img_np)
        for result in ocr_result:
            text += result[1] + "\n"

    else:
        raise ValueError(f"Unsupported file format: {file_ext}. Please provide a PDF or image file.")

    # Process the extracted text (assuming extract_vehicle_fields is defined elsewhere)
    extracted_data = extract_vehicle_fields(text, file_ext)
    return extracted_data

def extract_vehicle_fields(text: str,file_ext: str) -> dict:
    if file_ext == ".pdf":
        fields = {}

        # Registration number (look for "Registration" followed by letters/numbers)
        # First try explicit "A Registration" pattern
        reg_match = re.search(r"A\s*Registration\s*[\n:]*\s*([A-Z]{2}\d{2}\s?[A-Z]{3})", text, re.IGNORECASE)

        # If not found, try generic UK plate format anywhere in text
        if not reg_match:
            reg_match = re.search(r"\b([A-Z]{2}\d{2}\s?[A-Z]{3})\b", text)

        fields["registration"] = reg_match.group(1).strip() if reg_match else ""

        # D.1: Make
        make_match = re.search(r"(?:D\.1[:\s]*)?Make\s+([A-Z][A-Z0-9\- ]{1,20})", text)
        fields["make"] = make_match.group(1).strip() if make_match else ""

        # D.3: Model
        model_match = re.search(r"D\.3:\s*Model\s*(.+)", text)
        fields["model"] = model_match.group(1).strip() if model_match else ""

        # D.5: Body type
        body_match = re.search(r"D\.5:\s*Body type\s*([A-Z ]+)", text, re.IGNORECASE)
        fields["body_type"] = body_match.group(1).strip() if body_match else ""

        # R: Colour
        color_match = re.search(r"R:\s*Colour\s*([A-Z ]+)", text, re.IGNORECASE)
        fields["color"] = color_match.group(1).strip() if color_match else ""

        # P.1: Cylinder capacity (cc)
        engine_match = re.search(r"P\.?\s*1[:\s]*Cylinder capacity\s*\(cc\)\s*([0-9]{3,5})", text, re.IGNORECASE)

        # Fallback if OCR noise adds "CC" after number
        if not engine_match:
            engine_match = re.search(r"P\.?\s*1[:\s]*.*?([0-9]{3,5})\s*CC", text, re.IGNORECASE)

        fields["engine_size"] = engine_match.group(1).strip() if engine_match else ""

        # P.3: Type of fuel
        fuel_match = re.search(r"P\.?3:\s*Type of fuel\s*([A-Z ]+)", text, re.IGNORECASE)
        if fuel_match:
            fuel_type = fuel_match.group(1).strip()
        else:
            fuel_type = ""
        fields["fuel_type"] = fuel_type

        # S.1: Number of seats
        seat_match = re.search(r"No\. of seats\s*([0-9]{1,2})", text, re.IGNORECASE)
        if seat_match:
            num_seats = seat_match.group(1)
        else:
            num_seats = ""
        fields["Number of seats"]= num_seats

        # J: Vehicle category
        category_match = re.search(r"J:\s*Vehicle category\s*([A-Z0-9]+)", text, re.IGNORECASE)
        fields["vehicle_category"] = category_match.group(1).strip() if category_match else ""
        return fields
    elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
        fields = {}

        # Registration number
        reg_match = re.search(r"A\s*Registration\s*[\n:]*\s*([A-Z]{2}\d{2}\s?[A-Z]{3})", text, re.IGNORECASE)
        if not reg_match:
            reg_match = re.search(r"\b([A-Z]{2}\d{2}\s?[A-Z]{3})\b", text)
        fields["registration"] = reg_match.group(1).strip() if reg_match else ""

        # D.1: Make
        make_match = re.search(r"(?:D\.1[:\s]*)?Make\s+([A-Z][A-Z0-9\- ]{1,20})", text)
        fields["make"] = make_match.group(1).strip() if make_match else ""

        # D.3: Model
        model_match = re.search(r"D\.3:\s*Model\s*(.+)", text)
        fields["model"] = model_match.group(1).strip() if model_match else ""

        # D.5: Body type
        body_match = re.search(r"D\.5:\s*Body type\s*([A-Z ]+)", text, re.IGNORECASE)
        fields["body_type"] = body_match.group(1).strip() if body_match else ""

        # R: Colour
        color_match = re.search(r"R:\s*Colour\s*([A-Z ]+)", text, re.IGNORECASE)
        fields["color"] = color_match.group(1).strip() if color_match else ""

        # P.1: Cylinder capacity (cc)
        engine_match = re.search(r"P\.?\s*1[:\s]*Cylinder capacity\s*\(cc\)\s*([0-9]{3,5})", text, re.IGNORECASE)
        if not engine_match:
            engine_match = re.search(r"P\.?\s*1[:\s]*.*?([0-9]{3,5})\s*CC", text, re.IGNORECASE)
        fields["engine_size"] = engine_match.group(1).strip() if engine_match else ""

        # P.3: Type of fuel
        fuel_match = re.search(r"P\.?3:\s*Type of fuel\s*([A-Z ]+)", text, re.IGNORECASE)
        if fuel_match:
            fuel_type = fuel_match.group(1).strip()
        else:
            fuel_type = "Not found"
        fields["fuel_type"] = fuel_type  # Store the value, not the match object

        # S.1: Number of seats - handle OCR errors
        seat_match = re.search(r"No\. of seats\s*([0-9]{1,2})", text, re.IGNORECASE)
        if seat_match:
            num_seats = seat_match.group(1)
        else:
            num_seats = ""
        fields["Number of seats"] = num_seats

        # J: Vehicle category
        category_match = re.search(r"J:\s*Vehicle category\s*([A-Z0-9]+)", text, re.IGNORECASE)
        fields["vehicle_category"] = category_match.group(1).strip() if category_match else ""

        return fields


def _history_base_dir():
    # absolute base dir for storage
    return os.path.abspath(os.path.join(os.getcwd(), "uploads", "history"))

# Create a simple wrapper to process the file through the OCR service
class OCRService:
    def process_file(self, file, db, claim_id: int, actor_id: int):
        # Validate claim exists
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise ValueError(f"Claim with id {claim_id} does not exist")

        base_dir = _history_base_dir()
        # Ensure absolute base exists
        os.makedirs(base_dir, exist_ok=True)
        # timestamp folder
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        # uploads/history/<claim_id>/<client_vehicle>/<ts>
        target_dir = os.path.join(base_dir,str(claim_id),ts)
        os.makedirs(target_dir, exist_ok=True)

        # sanitize filename
        filename = file.filename or "file.bin"
        safe_filename = filename.replace("/", "_").replace("..", "_")
        sanitized_filename = urllib.parse.quote(safe_filename)

        # full path on disk
        full_path = os.path.join(target_dir, sanitized_filename)
        # Ensure the file is saved correctly
        with open(full_path, "wb") as out:
            out.write(file.file.read())

            # OCR extraction
        extracted_data = extract_text_from_file(full_path)

        # generate normalized relative path for DB
        rel_path = os.path.relpath(full_path, base_dir)
        stored_path = "/" + rel_path.replace("\\", "/")

        # history DB record
        history = HistoryActivities(
            claim_id=claim_id,
            file_name=sanitized_filename,
            file_path=stored_path,
            file_type=HistoryLogType.CLIENT_VEHICLE,
            created_by=actor_id,
            updated_by=actor_id,
        )

        db.add(history)
        db.commit()
        db.refresh(history)

        return extracted_data, stored_path, sanitized_filename


ocr_service = OCRService()
