from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import DepositRefundRequest, OnHireEmailRequest, PayHirerRequest
from fleet.models.tables import FleetHirePayment, FleetHireVehicle
from fleet.services import email_service
from fleet.services.common import get_hire_or_404

router = APIRouter()

# Attachment guard rails (defence against using this as a large-payload relay).
MAX_FILES = 10
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB per file
MAX_TOTAL_BYTES = 25 * 1024 * 1024  # 25 MB per email


def _num(v: Optional[str]) -> float:
    try:
        return float(str(v or "").replace("£", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _gbp(v: float) -> str:
    return f"£{v:.2f}"


def _ddmmyyyy(d) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _fleet_vehicles(db: Session, hire_id: int):
    vehicles = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.hire_id == hire_id)
        .order_by(FleetHireVehicle.position, FleetHireVehicle.id)
        .all()
    )
    return vehicles


def _latest_registration(db: Session, hire_id: int) -> str:
    vehicles = list(reversed(_fleet_vehicles(db, hire_id)))
    on_hire = next((v for v in vehicles if v.hire_status == "on_hire" and v.registration_number), None)
    latest = next((v for v in vehicles if v.registration_number), None)
    return (on_hire or latest).registration_number if (on_hire or latest) else ""


@router.post("/hire/{hire_id}/email")
async def send_hire_email_route(
    hire_id: int,
    to: str = Form(...),
    subject: str = Form(""),
    body: str = Form(""),
    cc: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    get_hire_or_404(db, hire_id, tenant_id)
    if "@" not in (to or ""):
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Too many attachments (max {MAX_FILES}).")

    attachments = []
    total = 0
    for f in files:
        content = await f.read()
        if not content:
            continue
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail=f"{f.filename or 'Attachment'} exceeds the 15 MB limit.")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(status_code=400, detail="Attachments exceed the 25 MB total limit.")
        attachments.append(email_service.build_attachment(f.filename, f.content_type, content))

    result = email_service.send_hire_email(to=to, subject=subject, body=body, attachments=attachments, cc=cc)
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("detail") or "Email failed to send.")
    return result


@router.post("/hire/{hire_id}/on-hire-email")
def on_hire_email_route(
    hire_id: int,
    payload: OnHireEmailRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Send the structured (boxed) on-hire confirmation email."""
    hire = get_hire_or_404(db, hire_id, tenant_id)
    if "@" not in (payload.to or ""):
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")
    data = {
        "driver_name": hire.driver_name,
        "registration": payload.registration,
        "make": payload.make,
        "model": payload.model,
        "hire_start": payload.hire_start,
    }
    subject = payload.subject or f"Vehicle On Hire - {payload.registration or ''}".strip()
    # Always send the structured (boxed) template — never the free-form `body`, which
    # renders as a run-on paragraph in Outlook. `body` is ignored for on-hire.
    result = email_service.send_on_hire_email(payload.to, subject, data, cc=payload.cc)
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("detail") or "Email failed to send.")
    return result


@router.get("/hire/{hire_id}/on-hire-email/preview")
def on_hire_email_preview_route(
    hire_id: int,
    registration: str = Query(""),
    make: str = Query(""),
    model: str = Query(""),
    hire_start: str = Query(""),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """The exact structured on-hire email HTML, without the embedded logo, for preview."""
    hire = get_hire_or_404(db, hire_id, tenant_id)
    data = {
        "driver_name": hire.driver_name,
        "registration": registration,
        "make": make,
        "model": model,
        "hire_start": hire_start,
    }
    return {"html": email_service.render_on_hire(data, include_logo=False)}


def _payment_totals(db: Session, hire_id: int) -> dict:
    rows = db.query(FleetHirePayment).filter(FleetHirePayment.hire_id == hire_id).all()
    total_due = sum(_num(row.due_amount) for row in rows)
    total_paid = sum(_num(row.paid_amount) for row in rows)
    adjusted = sum(
        _num(txn.amount)
        for row in rows
        for txn in (row.transactions or [])
        if (txn.payment_mode or "") == "security_deposit"
    )
    return {
        "total_due": total_due,
        "total_paid": total_paid,
        "unpaid": max(0.0, total_due - total_paid),
        "adjusted_from_deposit": adjusted,
    }


def _vehicle_refund_totals(db: Session, hire_id: int) -> dict:
    vehicles = _fleet_vehicles(db, hire_id)
    first_deposit = next((_num(v.deposit) for v in vehicles if _num(v.deposit) > 0), 0.0)
    registrations = ", ".join([v.registration_number for v in vehicles if v.registration_number])
    starts = [v.hire_start_date for v in vehicles if v.hire_start_date]
    ends = [v.hire_end_date for v in vehicles if v.hire_end_date]
    return {
        "deposit": first_deposit,
        "registration": registrations or "",
        "vehicle_damages": sum(_num(v.damage_charges) for v in vehicles),
        "additional_charges": sum(_num(v.additional_charges) for v in vehicles),
        "hire_start": min(starts) if starts else None,
        "hire_end": max(ends) if ends else None,
    }


def _payload_or_default(payload: Optional[DepositRefundRequest], field: str, default: float) -> float:
    if payload is not None:
        value = getattr(payload, field, None)
        if value is not None:
            return _num(value)
    return default


def _refund_data(db: Session, hire, payload: Optional[DepositRefundRequest] = None) -> dict:
    """Build the deposit-refund template data from the hire + optional editable
    inputs. Deduction line items we don't store default to 0."""
    p = payload or DepositRefundRequest(to="")
    vehicle_totals = _vehicle_refund_totals(db, hire.id)
    payment_totals = _payment_totals(db, hire.id)
    default_deposit = vehicle_totals["deposit"] or _num(hire.security_deposit) or _num(hire.deposit)
    deposit = _payload_or_default(payload, "deposit", default_deposit)
    valeting = _payload_or_default(payload, "valeting_fee", 0.0)
    damages = _payload_or_default(payload, "vehicle_damages", vehicle_totals["vehicle_damages"] or _num(hire.payment_damage_charges))
    additional = _payload_or_default(payload, "additional_charges", vehicle_totals["additional_charges"] or _num(hire.additional_charges))
    excess = _payload_or_default(payload, "excess_ppm", 0.0)
    unpaid = _payload_or_default(payload, "hire_charges_unpaid", payment_totals["unpaid"])
    adjusted = _payload_or_default(payload, "adjusted_from_deposit", payment_totals["adjusted_from_deposit"])
    charges_due_default = valeting + damages + additional + excess + unpaid
    charges_due = _payload_or_default(payload, "charges_due", charges_due_default)
    total_default = adjusted + charges_due
    total = _payload_or_default(payload, "total_deductions", total_default)
    refund = _payload_or_default(payload, "refund_amount", max(0.0, deposit - total))
    return {
        "ref": p.ref if p.ref is not None else hire.fleet_reference,
        "hirer_name": p.hirer_name if p.hirer_name is not None else hire.driver_name,
        "registration": p.registration or vehicle_totals["registration"] or hire.registration_number,
        "deposit": _gbp(deposit),
        "valeting_fee": _gbp(valeting),
        "vehicle_damages": _gbp(damages),
        "additional_charges": _gbp(additional),
        "excess_ppm": _gbp(excess),
        "hire_charges_unpaid": _gbp(unpaid),
        "adjusted_from_deposit": _gbp(adjusted),
        "charges_due": _gbp(charges_due),
        "total_deductions": _gbp(total),
        "refund_amount": _gbp(refund),
        "deposit_raw": f"{deposit:.2f}",
        "valeting_fee_raw": f"{valeting:.2f}",
        "vehicle_damages_raw": f"{damages:.2f}",
        "additional_charges_raw": f"{additional:.2f}",
        "excess_ppm_raw": f"{excess:.2f}",
        "hire_charges_unpaid_raw": f"{unpaid:.2f}",
        "adjusted_from_deposit_raw": f"{adjusted:.2f}",
        "charges_due_raw": f"{charges_due:.2f}",
        "total_deductions_raw": f"{total:.2f}",
        "refund_amount_raw": f"{refund:.2f}",
        "bank": p.bank if p.bank is not None else hire.bank_name,
        "account_name": p.account_name if p.account_name is not None else hire.account_name,
        "sort_code": p.sort_code if p.sort_code is not None else hire.sort_code,
        "account_number": p.account_number if p.account_number is not None else hire.account_number,
        "hire_start": p.hire_start if p.hire_start is not None else _ddmmyyyy(vehicle_totals["hire_start"] or hire.payment_hire_start_date),
        "hire_end": p.hire_end if p.hire_end is not None else _ddmmyyyy(vehicle_totals["hire_end"] or hire.payment_hire_end_date),
    }


def _pay_hirer_data(db: Session, hire, payload: PayHirerRequest) -> dict:
    return {
        "ref": hire.fleet_reference,
        "hirer_name": hire.driver_name,
        "registration": payload.registration or _latest_registration(db, hire.id),
        "amount": _gbp(_num(payload.amount)),
        "reason": payload.reason,
        "bank": hire.bank_name,
        "account_name": hire.account_name,
        "sort_code": hire.sort_code,
        "account_number": hire.account_number,
    }


@router.get("/hire/{hire_id}/deposit-refund/preview")
def deposit_refund_preview_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """The exact HTML the deposit-refund email will send (for the modal preview)."""
    hire = get_hire_or_404(db, hire_id, tenant_id)
    # Preview omits the logo (the sent email keeps it).
    data = _refund_data(db, hire)
    return {"html": email_service.render_deposit_refund(data, include_logo=False), "data": data}


@router.post("/hire/{hire_id}/deposit-refund")
def deposit_refund_route(
    hire_id: int,
    payload: DepositRefundRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    if "@" not in (payload.to or ""):
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")

    result = email_service.send_deposit_refund_email(
        payload.to, payload.subject or "Request Refund Deposit", _refund_data(db, hire, payload), cc=payload.cc
    )
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("detail") or "Email failed to send.")
    return result


@router.get("/hire/{hire_id}/pay-hirer/preview")
def pay_hirer_preview_route(
    hire_id: int,
    amount: str = Query(""),
    reason: str = Query(""),
    registration: Optional[str] = Query(None),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """The exact HTML the Pay/Reimburse Hirer email will send (for preview)."""
    hire = get_hire_or_404(db, hire_id, tenant_id)
    payload = PayHirerRequest(to="preview@example.com", amount=amount, reason=reason, registration=registration)
    return {"html": email_service.render_pay_hirer(_pay_hirer_data(db, hire, payload), include_logo=False)}


@router.post("/hire/{hire_id}/pay-hirer")
def pay_hirer_route(
    hire_id: int,
    payload: PayHirerRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    if "@" not in (payload.to or ""):
        raise HTTPException(status_code=400, detail="A valid recipient email is required.")
    if not payload.amount or _num(payload.amount) <= 0:
        raise HTTPException(status_code=400, detail="Amount to pay is required.")
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="Reason is required.")

    data = _pay_hirer_data(db, hire, payload)
    subject = payload.subject or f"Pay Hirer - {data.get('ref') or ''} {data.get('hirer_name') or ''}".strip()
    result = email_service.send_pay_hirer_email(payload.to, subject, data, cc=payload.cc)
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("detail") or "Email failed to send.")
    return result
