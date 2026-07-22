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
async def ocr_taxi_badge_route(file: UploadFile = File(...), debug: bool = False):
    """OCR a UK taxi (private-hire / hackney) driver badge into badge fields.

    Pass ?debug=true to also return the raw OCR text — badges are photographed
    laminated cards, often with a security hologram over the name, so the raw
    read is the only reliable way to see why a field extracted wrongly.
    """
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    result = fleet_ocr.parse_taxi_badge(text)
    if debug:
        result["_raw_text"] = text
    return result


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


@router.post("/ocr/v5c")
async def ocr_v5c_route(file: UploadFile = File(...)):
    """OCR a V5C logbook into vehicle fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_v5c(text)


@router.post("/ocr/plating-certificate")
async def ocr_plating_certificate_route(file: UploadFile = File(...)):
    """OCR a plating expiry certificate into authority + plating fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_plating_certificate(text)


@router.post("/ocr/mot-certificate")
async def ocr_mot_certificate_route(file: UploadFile = File(...)):
    """OCR an MOT certificate into MOT centre + MOT date fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_mot_certificate(text)


@router.post("/ocr/service-invoice")
async def ocr_service_invoice_route(file: UploadFile = File(...)):
    """OCR a garage service invoice into garage + servicing fields."""
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    return fleet_ocr.parse_service_invoice(text)
