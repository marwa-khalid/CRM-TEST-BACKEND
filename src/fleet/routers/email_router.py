from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import DepositRefundRequest, OnHireEmailRequest, PayHirerRequest
from fleet.models.tables import FleetHireVehicle
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


def _latest_registration(db: Session, hire_id: int) -> str:
    vehicles = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.hire_id == hire_id)
        .order_by(FleetHireVehicle.id.desc())
        .all()
    )
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
    subject = payload.subject or f"Your Vehicle is Now On Hire - {payload.registration or ''}".strip()
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


def _refund_data(hire, payload: Optional[DepositRefundRequest] = None) -> dict:
    """Build the deposit-refund template data from the hire + optional editable
    inputs. Deduction line items we don't store default to 0."""
    p = payload or DepositRefundRequest(to="")
    deposit = _num(hire.security_deposit)
    valeting = _num(p.valeting_fee)
    damages = _num(p.vehicle_damages if p.vehicle_damages is not None else hire.payment_damage_charges)
    excess = _num(p.excess_ppm)
    unpaid = _num(p.hire_charges_unpaid)
    total = valeting + damages + excess + unpaid
    refund = max(0.0, deposit - total)
    return {
        "ref": hire.fleet_reference,
        "hirer_name": hire.driver_name,
        "registration": p.registration or hire.registration_number,
        "deposit": _gbp(deposit),
        "valeting_fee": _gbp(valeting),
        "vehicle_damages": _gbp(damages),
        "excess_ppm": _gbp(excess),
        "hire_charges_unpaid": _gbp(unpaid),
        "total_deductions": _gbp(total),
        "refund_amount": _gbp(refund),
        "bank": hire.bank_name,
        "account_name": hire.account_name,
        "sort_code": hire.sort_code,
        "account_number": hire.account_number,
        "hire_start": _ddmmyyyy(hire.payment_hire_start_date),
        "hire_end": _ddmmyyyy(hire.payment_hire_end_date),
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
    return {"html": email_service.render_deposit_refund(_refund_data(hire), include_logo=False)}


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
        payload.to, payload.subject or "Request Refund Deposit", _refund_data(hire, payload), cc=payload.cc
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
