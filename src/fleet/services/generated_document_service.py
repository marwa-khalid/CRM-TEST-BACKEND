"""Generated Fleet document assets.

These files live inside the Fleet module so Fleet stays separable from Claims.
For now the Raise Hire Documentation source files are static Office documents
from ``fleet/assets/Documents``; this service exposes them through authenticated
Fleet routes for download/email attachment.
"""
from dataclasses import dataclass
from io import BytesIO
import mimetypes
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.models.tables import FleetHireVehicle
from fleet.services.common import get_hire_or_404


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "Documents"


@dataclass(frozen=True)
class GeneratedDocumentAsset:
    key: str
    filename: str
    source_filename: str

    @property
    def path(self) -> Path:
        return ASSET_DIR / self.source_filename

    @property
    def content_type(self) -> str:
        return mimetypes.guess_type(self.filename)[0] or "application/octet-stream"


DOCUMENT_GROUPS: Dict[str, List[GeneratedDocumentAsset]] = {
    "raise_hire_documentation": [
        GeneratedDocumentAsset(
            key="raise_hire_documentation_docx",
            filename="Raise Hire Documentation.docx",
            source_filename="Raise Hire Documentation .docx",
        ),
        GeneratedDocumentAsset(
            key="raise_hire_documentation_xls",
            filename="Raise Hire Documentation II.xls",
            source_filename="Raise Hire Documentation II.xls",
        ),
    ],
    "raise_authority_letter": [
        GeneratedDocumentAsset(
            key="raise_authority_letter_docx",
            filename="Raise Authority Letter.docx",
            source_filename="Raise Authority Letter.docx",
        ),
    ],
    "raise_vehicle_inspection_sheet": [
        GeneratedDocumentAsset(
            key="raise_vehicle_inspection_sheet_xlsx",
            filename="Vehicle Inspection Sheet.xlsx",
            source_filename="Vehicle Inspection Sheet.xlsx",
        ),
    ],
}


def _assets_for(document_key: str) -> List[GeneratedDocumentAsset]:
    assets = DOCUMENT_GROUPS.get(document_key)
    if not assets:
        raise HTTPException(status_code=404, detail="Generated document not found")
    missing = [asset.filename for asset in assets if not asset.path.exists()]
    if missing:
        raise HTTPException(status_code=404, detail=f"Document asset missing: {', '.join(missing)}")
    return assets


def list_document_files(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    document_key: str,
    vehicle_id: Optional[int] = None,
) -> List[dict]:
    hire, vehicle = _get_hire_and_vehicle(db, hire_id, tenant_id, vehicle_id)
    context = _document_context(hire, vehicle)
    return [
        {
            "key": asset.key,
            "filename": asset.filename,
            "content_type": asset.content_type,
            "size": len(_render_asset(asset, context)),
        }
        for asset in _assets_for(document_key)
    ]


def get_document_file(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    document_key: str,
    file_key: str,
    vehicle_id: Optional[int] = None,
) -> Tuple[bytes, str, str]:
    hire, vehicle = _get_hire_and_vehicle(db, hire_id, tenant_id, vehicle_id)
    asset = next((item for item in _assets_for(document_key) if item.key == file_key), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Generated document file not found")
    return _render_asset(asset, _document_context(hire, vehicle)), asset.content_type, asset.filename


def get_document_bundle(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    document_key: str,
    vehicle_id: Optional[int] = None,
) -> Tuple[bytes, str, str]:
    hire, vehicle = _get_hire_and_vehicle(db, hire_id, tenant_id, vehicle_id)
    context = _document_context(hire, vehicle)
    assets = _assets_for(document_key)
    if len(assets) == 1:
        asset = assets[0]
        return _render_asset(asset, context), asset.content_type, asset.filename

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as zf:
        for asset in assets:
            zf.writestr(asset.filename, _render_asset(asset, context))
    return output.getvalue(), "application/zip", f"{document_key.replace('_', ' ').title()}.zip"


def _get_hire_and_vehicle(db: Session, hire_id: int, tenant_id: Optional[int], vehicle_id: Optional[int]):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    query = db.query(FleetHireVehicle).filter(FleetHireVehicle.hire_id == hire_id)
    if vehicle_id:
        query = query.filter(FleetHireVehicle.id == vehicle_id)
    vehicle = query.order_by(FleetHireVehicle.position, FleetHireVehicle.id).first()
    if vehicle_id and not vehicle:
        raise HTTPException(status_code=404, detail="Hire vehicle not found")
    return hire, vehicle


def _format_date(value) -> str:
    if not value:
        return ""
    try:
        return value.strftime("%d/%m/%Y")
    except AttributeError:
        return str(value)


def _date_time(value, time_value) -> str:
    parts = [_format_date(value), str(time_value or "").strip()]
    return " ".join(part for part in parts if part)


def _money_number(value) -> Optional[float]:
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _format_money(value) -> str:
    number = _money_number(value)
    if number is None:
        return ""
    return f"£{number:.2f}"


def _format_money_plain(value) -> str:
    number = _money_number(value)
    if number is None:
        return ""
    return f"{number:.2f}"


def _address_line(hire) -> str:
    return ", ".join(part.strip() for part in [hire.driver_address, hire.driver_postcode] if part and str(part).strip())


def _document_context(hire, vehicle: Optional[FleetHireVehicle]) -> dict:
    weekly = (
        getattr(vehicle, "vehicle_cost_per_week", None)
        or getattr(hire, "weekly_hire_payment", None)
        or getattr(hire, "vehicle_cost_per_week", None)
    )
    deposit = (
        getattr(vehicle, "deposit", None)
        or getattr(hire, "security_deposit", None)
        or getattr(hire, "deposit", None)
    )
    total_due_number = (_money_number(weekly) or 0) + (_money_number(deposit) or 0)
    start_date = getattr(vehicle, "hire_start_date", None) or getattr(hire, "payment_hire_start_date", None) or getattr(hire, "hire_start_date", None)
    end_date = (
        getattr(vehicle, "hire_end_date", None)
        or getattr(vehicle, "checkout_date", None)
        or getattr(hire, "payment_hire_end_date", None)
        or getattr(hire, "hire_end_date", None)
    )
    start_time = getattr(vehicle, "hire_start_time", None)
    end_time = getattr(vehicle, "checkout_time", None)
    make = (getattr(vehicle, "make", None) or getattr(hire, "make", None) or "").strip()
    model = (getattr(vehicle, "model", None) or getattr(hire, "model", None) or "").strip()

    return {
        "hirer_name": (hire.driver_name or "").strip(),
        "hirer_address": (hire.driver_address or "").strip(),
        "hirer_postcode": (hire.driver_postcode or "").strip(),
        "hirer_full": " of ".join(part for part in [(hire.driver_name or "").strip(), _address_line(hire)] if part),
        "date_of_birth": _format_date(hire.date_of_birth),
        "driving_licence_number": (hire.driving_licence_number or "").strip(),
        "licence_expiry": _format_date(hire.driving_licence_end),
        "make": make,
        "model": model,
        "vehicle_description": " ".join(part for part in [make, model] if part),
        "registration": (getattr(vehicle, "registration_number", None) or getattr(hire, "registration_number", None) or "").strip(),
        "hire_start": _date_time(start_date, start_time),
        "hire_start_date": _format_date(start_date),
        "hire_start_time": str(start_time or "").strip(),
        "hire_end": _date_time(end_date, end_time),
        "hire_end_date": _format_date(end_date),
        "hire_end_time": str(end_time or "").strip(),
        "weekly": _format_money(weekly),
        "weekly_plain": _format_money_plain(weekly),
        "weekly_number": _money_number(weekly),
        "deposit": _format_money(deposit),
        "deposit_plain": _format_money_plain(deposit),
        "deposit_number": _money_number(deposit),
        "total_due": f"£{total_due_number:.2f}" if total_due_number else "",
        "total_due_number": total_due_number if total_due_number else None,
    }


def _set_paragraph_text(paragraph, text: str):
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _replace_sample_text(text: str, ctx: dict) -> str:
    address = ", ".join(part for part in [ctx["hirer_address"], ctx["hirer_postcode"]] if part)
    replacements = {
        "Mr SabER Mehrabi": ctx["hirer_name"],
        "54 Highfields court t , Leasowes Drive , WV44PZ": address,
        "54 Highfields court t , Leasowes Drive": ctx["hirer_address"],
        "54 Highfields court t \nLeasowes Drive": ctx["hirer_address"],
        "WV44PZ": ctx["hirer_postcode"],
        "MEHRA901276S99ZM 49": ctx["driving_licence_number"],
        "13/07/26": ctx["hire_start_date"],
        "13/07/2026": ctx["hire_start"],
        "03/02/2026": ctx["hire_end"],
        "£300.00": ctx["deposit"],
        "£230.00": ctx["weekly"],
    }
    updated = text
    for old, new in replacements.items():
        if new:
            updated = updated.replace(old, new)
    if ctx["registration"]:
        updated = re.sub(r"vehicle registration\s*,", f"vehicle registration {ctx['registration']},", updated, flags=re.I)
        updated = re.sub(
            r"vehicle registration\s+from Skyline",
            f"vehicle registration {ctx['registration']} from Skyline",
            updated,
            flags=re.I,
        )
    return updated


def _render_docx(asset: GeneratedDocumentAsset, ctx: dict) -> bytes:
    from docx import Document

    doc = Document(asset.path)
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if text.startswith("Hirer/Lessee"):
            _set_paragraph_text(paragraph, f"Hirer/Lessee (you/your) - \t{ctx['hirer_full']}")
        elif text.startswith("Full Name:") and "of" in text:
            _set_paragraph_text(paragraph, f"Full Name: \t\t{ctx['hirer_full']}")
        elif text.startswith("Full Name:"):
            _set_paragraph_text(paragraph, f"Full Name: {ctx['hirer_name']}")
        elif text.startswith("Driver Name:"):
            _set_paragraph_text(paragraph, f"Driver Name:\t\t\t{ctx['hirer_name']}")
        elif text.startswith("Address:") and any(sample in text for sample in ["54 Highfields", "Leasowes", "WV44PZ"]):
            _set_paragraph_text(paragraph, f"Address:\t\t\t{', '.join(part for part in [ctx['hirer_address'], ctx['hirer_postcode']] if part)}")
        elif text.startswith("Vehicle Registration:"):
            _set_paragraph_text(paragraph, f"Vehicle Registration:\t{ctx['registration']}")
        elif text.startswith("Make & Model:"):
            _set_paragraph_text(paragraph, f"Make & Model:\t\t{ctx['vehicle_description']}")
        elif text.startswith("Hire Start Date:"):
            _set_paragraph_text(paragraph, f"Hire Start Date: {ctx['hire_start']} \tHire End Date: {ctx['hire_end']}")
        elif text.startswith("Vehicle Description (Make/Model)"):
            _set_paragraph_text(paragraph, f"Vehicle Description (Make/Model) -\t{ctx['vehicle_description']}")
        elif text.startswith("Vehicle Registration Number"):
            _set_paragraph_text(paragraph, f"Vehicle Registration Number -\t{ctx['registration']}")
        elif text.startswith("Agreement Start Date"):
            _set_paragraph_text(paragraph, f"Agreement Start Date -\t{ctx['hire_start']}")
        elif text.startswith("Security Deposit"):
            _set_paragraph_text(paragraph, f"Security Deposit -\t\t\t\t{ctx['deposit']}")
        elif text.startswith("Payment Profile"):
            _set_paragraph_text(paragraph, f"Payment Profile -\tWeekly payments of {ctx['weekly']} Inc VAT/IPT")
        elif text.startswith("Hirer Name:"):
            _set_paragraph_text(paragraph, f"Hirer Name: {ctx['hirer_name']} \tDate: {ctx['hire_start']}")
        else:
            updated = _replace_sample_text(paragraph.text, ctx)
            if updated != paragraph.text:
                _set_paragraph_text(paragraph, updated)

    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def _write_xls(ws, row: int, col: int, value):
    if value is not None:
        ws.write(row, col, value)


def _render_hire_documentation_xls(asset: GeneratedDocumentAsset, ctx: dict) -> bytes:
    import xlrd
    from xlutils.copy import copy

    book = xlrd.open_workbook(str(asset.path), formatting_info=True)
    writable = copy(book)
    ws = writable.get_sheet(0)

    _write_xls(ws, 10, 4, ctx["hirer_name"])
    _write_xls(ws, 12, 4, ctx["hirer_address"])
    _write_xls(ws, 18, 4, ctx["hirer_postcode"])
    _write_xls(ws, 20, 4, ctx["date_of_birth"])
    _write_xls(ws, 22, 4, ctx["driving_licence_number"])
    _write_xls(ws, 25, 5, ctx["licence_expiry"])

    _write_xls(ws, 18, 9, ctx["make"])
    _write_xls(ws, 18, 13, ctx["model"])
    _write_xls(ws, 20, 9, ctx["registration"])
    _write_xls(ws, 22, 9, ctx["hire_start_date"])
    _write_xls(ws, 22, 13, ctx["hire_start_time"])
    _write_xls(ws, 25, 9, ctx["hire_end_date"])
    _write_xls(ws, 25, 13, ctx["hire_end_time"])

    _write_xls(ws, 34, 4, ctx["hirer_name"])
    _write_xls(ws, 40, 4, ctx["hirer_address"])
    _write_xls(ws, 51, 4, ctx["hirer_postcode"])
    _write_xls(ws, 34, 11, ctx["weekly_number"])
    _write_xls(ws, 37, 11, ctx["deposit_number"])
    _write_xls(ws, 40, 11, ctx["total_due_number"])

    for row, col in [(77, 12), (83, 5), (100, 5), (100, 12), (110, 10)]:
        _write_xls(ws, row, col, ctx["hire_start_date"])
    _write_xls(ws, 110, 6, ctx["hirer_name"])

    output = BytesIO()
    writable.save(output)
    return output.getvalue()


def _render_vehicle_inspection_xlsx(asset: GeneratedDocumentAsset, ctx: dict) -> bytes:
    from openpyxl import load_workbook

    workbook = load_workbook(asset.path)
    sheet = workbook.active
    sheet["D5"] = ctx["hirer_name"]
    sheet["D7"] = ctx["hirer_address"]
    sheet["D13"] = ctx["hirer_postcode"]
    sheet["D19"] = ctx["vehicle_description"]
    sheet["K19"] = ctx["registration"]
    sheet["C23"] = ctx["hire_start_date"]
    sheet["C25"] = ctx["hire_start_time"]
    sheet["J23"] = ctx["hire_end_date"]
    sheet["J25"] = ctx["hire_end_time"]
    sheet["D80"] = ctx["hirer_name"]

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _render_asset(asset: GeneratedDocumentAsset, context: dict) -> bytes:
    if asset.source_filename.lower().endswith(".docx"):
        return _render_docx(asset, context)
    if asset.source_filename == "Raise Hire Documentation II.xls":
        return _render_hire_documentation_xls(asset, context)
    if asset.source_filename == "Vehicle Inspection Sheet.xlsx":
        return _render_vehicle_inspection_xlsx(asset, context)
    return asset.path.read_bytes()
