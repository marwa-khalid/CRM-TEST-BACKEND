from fastapi import APIRouter, File, UploadFile

from fleet.services import ocr as fleet_ocr

router = APIRouter()


@router.get("/ocr/env")
def ocr_env_route():
    """Diagnostic: which OCR engine + language data THIS instance runs. Hit it on
    localhost and on the deployed URL and compare — the tesseract version AND the
    eng.traineddata hash both affect the result (same version + different language
    data still OCRs differently)."""
    import hashlib
    import os
    import platform

    info = {"platform": platform.platform(), "python": platform.python_version()}
    try:
        import pytesseract

        info["tesseract_version"] = str(pytesseract.get_tesseract_version())
        try:
            info["languages"] = pytesseract.get_languages()
        except Exception as exc:  # pragma: no cover - diagnostic only
            info["languages"] = f"error: {exc}"
    except Exception as exc:  # pragma: no cover - diagnostic only
        info["tesseract_version"] = f"error: {exc}"

    # eng.traineddata identity — size + short hash tells you if local vs deployed
    # use a DIFFERENT language model, which is the usual reason results diverge.
    for d in (
        os.environ.get("TESSDATA_PREFIX", ""),
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
        "/usr/local/share/tessdata",
        "/opt/homebrew/share/tessdata",
    ):
        p = os.path.join(d, "eng.traineddata") if d else ""
        if p and os.path.exists(p):
            data = open(p, "rb").read()
            info["eng_traineddata"] = {"path": p, "bytes": len(data), "sha256_12": hashlib.sha256(data).hexdigest()[:12]}
            break
    else:
        info["eng_traineddata"] = "eng.traineddata not found in known dirs"

    info["vision_key_set"] = bool(os.getenv("GOOGLE_VISION_API_KEY", "").strip())
    return info


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
    text = fleet_ocr.taxi_badge_file_to_text(await file.read(), file.filename or "")
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
async def ocr_v5c_route(file: UploadFile = File(...), debug: bool = False):
    """OCR a V5C logbook into vehicle fields.

    Pass ?debug=true to also return the raw OCR text, which is useful when a
    deployed environment reads a PDF differently from localhost.
    """
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    result = fleet_ocr.parse_v5c(text)
    if debug:
        result["_raw_text"] = text
    return result


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
async def ocr_service_invoice_route(file: UploadFile = File(...), debug: bool = False):
    """OCR a garage service invoice into garage + servicing fields.

    Pass ?debug=true to also return the raw OCR text for deployed OCR checks.
    """
    text = fleet_ocr.file_to_text(await file.read(), file.filename or "")
    result = fleet_ocr.parse_service_invoice(text)
    if debug:
        result["_raw_text"] = text
    return result
