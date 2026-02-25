# import os
# import urllib.parse
# import re
# import easyocr
# from PIL import Image
# import numpy as np
# from io import BytesIO
# from pdf2image import convert_from_path
# import pdf2image
# # EasyOCR reader initialization
# reader = easyocr.Reader(['en'])

# UPLOAD_DIR = "uploads"  # Directory to store uploaded files

# # Ensure the uploads directory exists
# if not os.path.exists(UPLOAD_DIR):
#     os.makedirs(UPLOAD_DIR)

# os.environ["PATH"] += os.pathsep + "/usr/local/opt/poppler/bin"

# def extract_text_from_file(file_path: str):
#     """
#     Extract text from either a PDF or image file and process it.

#     Args:
#         file_path (str): Path to the file to be processed

#     Returns:
#         dict: Extracted data after processing
#     """
#     # Check if file exists
#     if not os.path.exists(file_path):
#         raise FileNotFoundError(f"The file {file_path} does not exist.")

#     # Get file extension to determine type
#     file_ext = os.path.splitext(file_path)[1].lower()

#     text = ""

#     # Process PDF files
#     if file_ext == '.pdf':
#         import urllib.parse
#         clean_path = urllib.parse.unquote(file_path)
#         # 2. Point to the BIN folder inside your poppler directory
#         # Verify if your bin is actually in this subfolder:
#         images = pdf2image.convert_from_path(
#             clean_path
#         )
#         print(file_path)
#         print("marwa")
#         # Convert PDF to images (one image per page)
#         # images = pdf2image.pdf2image.convert_from_path(file_path,poppler_path=r'/Users/apple/Documents/GitHub/CRM_BACKEND/src/appflow/services/poppler-25.12.0')
        

#         for page in images:
#             img = BytesIO()
#             page.save(img, format='PNG')
#             img.seek(0)

#             # Convert BytesIO object to a format that EasyOCR can read (NumPy array)
#             img_pil = Image.open(img)
#             img_np = np.array(img_pil)

#             # Use EasyOCR to extract text from the image
#             ocr_result = reader.readtext(img_np)
#             for result in ocr_result:
#                 text += result[1] + "\n"

#     # Process image files (common formats)
#     elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
#         # Open the image file directly and convert it to NumPy array
#         img = Image.open(file_path)
#         img_np = np.array(img)

#         # Use EasyOCR to extract text from the image
#         ocr_result = reader.readtext(img_np)
#         for result in ocr_result:
#             text += result[1] + "\n"

#     else:
#         raise ValueError(f"Unsupported file format: {file_ext}. Please provide a PDF or image file.")

#     # Process the extracted text (assuming extract_vehicle_fields is defined elsewhere)
#     extracted_data = extract_vehicle_fields(text, file_ext)
#     print("OCR Text:\n", text)
#     return extracted_data

# def extract_vehicle_fields(text: str,file_ext: str) -> dict:
#     if file_ext == ".pdf":
#         fields = {}

#         # Registration number (look for "Registration" followed by letters/numbers)
#         # First try explicit "A Registration" pattern
#         reg_match = re.search(r"A\s*Registration\s*[\n:]*\s*([A-Z]{2}\d{2}\s?[A-Z]{3})", text, re.IGNORECASE)

#         # If not found, try generic UK plate format anywhere in text
#         if not reg_match:
#             reg_match = re.search(r"\b([A-Z]{2}\d{2}\s?[A-Z]{3})\b", text)

#         fields["registration"] = reg_match.group(1).strip() if reg_match else ""

#         # D.1: Make
#         make_match = re.search(r"(?:D\.1[:\s]*)?Make\s+([A-Z][A-Z0-9\- ]{1,20})", text)
#         fields["make"] = make_match.group(1).strip() if make_match else ""

#         # D.3: Model
#         model_match = re.search(r"D\.3:\s*Model\s*(.+)", text)
#         fields["model"] = model_match.group(1).strip() if model_match else ""

#         # D.5: Body type
#         body_match = re.search(r"D\.5:\s*Body type\s*([A-Z ]+)", text, re.IGNORECASE)
#         fields["body_type"] = body_match.group(1).strip() if body_match else ""

#         # R: Colour
#         color_match = re.search(r"R:\s*Colour\s*([A-Z ]+)", text, re.IGNORECASE)
#         fields["color"] = color_match.group(1).strip() if color_match else ""

#         # P.1: Cylinder capacity (cc)
#         engine_match = re.search(r"P\.?\s*1[:\s]*Cylinder capacity\s*\(cc\)\s*([0-9]{3,5})", text, re.IGNORECASE)

#         # Fallback if OCR noise adds "CC" after number
#         if not engine_match:
#             engine_match = re.search(r"P\.?\s*1[:\s]*.*?([0-9]{3,5})\s*CC", text, re.IGNORECASE)

#         fields["engine_size"] = engine_match.group(1).strip() if engine_match else ""

#         # P.3: Type of fuel
#         fuel_match = re.search(r"P\.?3:\s*Type of fuel\s*([A-Z ]+)", text, re.IGNORECASE)
#         if fuel_match:
#             fuel_type = fuel_match.group(1).strip()
#         else:
#             fuel_type = ""
#         fields["fuel_type"] = fuel_type

#         # S.1: Number of seats
#         seat_match = re.search(r"No\. of seats\s*([0-9]{1,2})", text, re.IGNORECASE)
#         if seat_match:
#             num_seats = seat_match.group(1)
#         else:
#             num_seats = ""
#         fields["Number of seats"]= num_seats

#         # J: Vehicle category
#         category_match = re.search(r"J:\s*Vehicle category\s*([A-Z0-9]+)", text, re.IGNORECASE)
#         fields["vehicle_category"] = category_match.group(1).strip() if category_match else ""
#         return fields
#     elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
#         fields = {}

#         # Registration number
#         reg_match = re.search(r"A\s*Registration\s*[\n:]*\s*([A-Z]{2}\d{2}\s?[A-Z]{3})", text, re.IGNORECASE)
#         if not reg_match:
#             reg_match = re.search(r"\b([A-Z]{2}\d{2}\s?[A-Z]{3})\b", text)
#         fields["registration"] = reg_match.group(1).strip() if reg_match else ""

#         # D.1: Make
#         make_match = re.search(r"(?:D\.1[:\s]*)?Make\s+([A-Z][A-Z0-9\- ]{1,20})", text)
#         fields["make"] = make_match.group(1).strip() if make_match else ""

#         # D.3: Model
#         model_match = re.search(r"D\.3:\s*Model\s*(.+)", text)
#         fields["model"] = model_match.group(1).strip() if model_match else ""

#         # D.5: Body type
#         body_match = re.search(r"D\.5:\s*Body type\s*([A-Z ]+)", text, re.IGNORECASE)
#         fields["body_type"] = body_match.group(1).strip() if body_match else ""

#         # R: Colour
#         color_match = re.search(r"R:\s*Colour\s*([A-Z ]+)", text, re.IGNORECASE)
#         fields["color"] = color_match.group(1).strip() if color_match else ""

#         # P.1: Cylinder capacity (cc)
#         engine_match = re.search(r"P\.?\s*1[:\s]*Cylinder capacity\s*\(cc\)\s*([0-9]{3,5})", text, re.IGNORECASE)
#         if not engine_match:
#             engine_match = re.search(r"P\.?\s*1[:\s]*.*?([0-9]{3,5})\s*CC", text, re.IGNORECASE)
#         fields["engine_size"] = engine_match.group(1).strip() if engine_match else ""

#         # P.3: Type of fuel
#         fuel_match = re.search(r"P\.?3:\s*Type of fuel\s*([A-Z ]+)", text, re.IGNORECASE)
#         if fuel_match:
#             fuel_type = fuel_match.group(1).strip()
#         else:
#             fuel_type = "Not found"
#         fields["fuel_type"] = fuel_type  # Store the value, not the match object

#         # S.1: Number of seats - handle OCR errors
#         seat_match = re.search(r"No\. of seats\s*([0-9]{1,2})", text, re.IGNORECASE)
#         if seat_match:
#             num_seats = seat_match.group(1)
#         else:
#             num_seats = ""
#         fields["Number of seats"] = num_seats

#         # J: Vehicle category
#         category_match = re.search(r"J:\s*Vehicle category\s*([A-Z0-9]+)", text, re.IGNORECASE)
#         fields["vehicle_category"] = category_match.group(1).strip() if category_match else ""

#         return fields


# # Create a simple wrapper to process the file through the OCR service
# class OCRService:
#     def process_file(self, file):
#         # Sanitize the filename by encoding spaces and special characters
#         sanitized_filename = urllib.parse.quote(file.filename)

#         file_path = os.path.join(UPLOAD_DIR, sanitized_filename)
#         print("marwa")
#         print("marwa")
#         print("marwa")
#         print("marwa")
#         print(file_path)
#         print("marwa")
#         print("marwa")
#         print("marwa")
#         print("marwa")
#         print("marwa")
#         # Ensure the file is saved correctly
#         with open(file_path, "wb") as f:
#             f.write(file.file.read())

#         # Check if it's a PDF or image and extract text accordingly
#         if file.filename.lower().endswith('.pdf'):
#             return extract_text_from_file(file_path)
#         elif file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
#             return extract_text_from_file(file_path)
#         return {}


# ocr_service = OCRService()
import os
import urllib.parse
import re
# import easyocr
from PIL import Image
import numpy as np
from io import BytesIO
import fitz  # Replacement for pdf2image (PyMuPDF)

# EasyOCR reader initialization
# reader = pytesseract.image_to_string(img_pil)
# reader = easyocr.Reader(['en'])

UPLOAD_DIR = "uploads"
import pytesseract
import shutil
import os

# 1. Try to find it automatically
tesseract_path = shutil.which("tesseract")

# 2. If automatic search fails, hardcode the Homebrew paths
if not tesseract_path:
    possible_paths = [
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract"
    ]
    for p in possible_paths:
        if os.path.exists(p):
            tesseract_path = p
            break

# 3. Assign it to the pytesseract config
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    print(f"Tesseract found at: {tesseract_path}")
else:
    print("CRITICAL: Tesseract still not found. Run 'brew install tesseract' in terminal.")
# Ensure the uploads directory exists
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

def extract_text_from_file(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    file_ext = os.path.splitext(file_path)[1].lower()
    text = ""
    clean_path = urllib.parse.unquote(file_path)

    try:
        if file_ext == '.pdf':
            # Open PDF using PyMuPDF (Native, no Poppler needed)
            with fitz.open(clean_path) as doc:
                for page in doc:
                    # 1. Try to get text directly first (Fastest & Most Accurate)
                    page_text = page.get_text()
                    
                    if page_text.strip():
                        text += page_text + "\n"
                    else:
                        # 2. If no text (it's a scan), use OCR
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img_pil = Image.open(BytesIO(pix.tobytes("png")))
                        text += pytesseract.image_to_string(img_pil) + "\n"

        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            # Process image directly
            img_pil = Image.open(clean_path)
            text = pytesseract.image_to_string(img_pil)

        else:
            raise ValueError(f"Unsupported format: {file_ext}")

    except Exception as e:
        print(f"Extraction Error: {e}")
        return {"error": str(e)}

    # Process the final text with your regex logic
    extracted_data = extract_vehicle_fields(text, file_ext)
    return extracted_data
# Keep your existing extract_vehicle_fields logic exactly as it was
def extract_vehicle_fields(text: str, file_ext: str) -> dict:
    # ... (Keep your entire regex logic here, it is unchanged)
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

    # P.1: Cylinder capacity
    engine_match = re.search(r"P\.?\s*1[:\s]*Cylinder capacity\s*\(cc\)\s*([0-9]{3,5})", text, re.IGNORECASE)
    if not engine_match:
        engine_match = re.search(r"P\.?\s*1[:\s]*.*?([0-9]{3,5})\s*CC", text, re.IGNORECASE)
    fields["engine_size"] = engine_match.group(1).strip() if engine_match else ""

    # P.3: Fuel
    fuel_match = re.search(r"P\.?3:\s*Type of fuel\s*([A-Z ]+)", text, re.IGNORECASE)
    fields["fuel_type"] = fuel_match.group(1).strip() if fuel_match else ""

    # S.1: Seats
    seat_match = re.search(r"No\. of seats\s*([0-9]{1,2})", text, re.IGNORECASE)
    fields["Number of seats"] = seat_match.group(1) if seat_match else ""

    # J: Category
    category_match = re.search(r"J:\s*Vehicle category\s*([A-Z0-9]+)", text, re.IGNORECASE)
    fields["vehicle_category"] = category_match.group(1).strip() if category_match else ""

    return fields

class OCRService:
    def process_file(self, file):
        # Decode the filename immediately to prevent "File not found" errors
        # Python's OS library prefers regular strings over quoted URLs
        clean_filename = urllib.parse.unquote(file.filename)
        file_path = os.path.join(UPLOAD_DIR, clean_filename)

        with open(file_path, "wb") as f:
            f.write(file.file.read())

        return extract_text_from_file(file_path)

ocr_service = OCRService()
