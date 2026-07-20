from fastapi import APIRouter, File, UploadFile

from fleet.services import ocr as fleet_ocr

router = APIRouter()


@router.post("/ocr/driving-licence")
async def ocr_driving_licence_route(file: UploadFile = File(...)):
    """OCR a driving-licence image/PDF into driver fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_driving_licence(text)


@router.post("/ocr/proof-of-address")
async def ocr_proof_of_address_route(file: UploadFile = File(...)):
    """OCR a proof-of-address image/PDF into address fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_proof_of_address(text)


@router.post("/ocr/taxi-badge")
async def ocr_taxi_badge_route(file: UploadFile = File(...)):
    """OCR a UK taxi (private-hire / hackney) driver badge into badge fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_taxi_badge(text)


@router.post("/ocr/insurance-certificate")
async def ocr_insurance_certificate_route(file: UploadFile = File(...)):
    """OCR an insurance certificate into policy start/end dates."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_insurance_certificate(text)


@router.post("/ocr/payment-receipt")
async def ocr_payment_receipt_route(file: UploadFile = File(...)):
    """OCR a bank transfer receipt into payment fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_payment_receipt(text)
