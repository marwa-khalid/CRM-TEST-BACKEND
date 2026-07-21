from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import FleetWhatsAppRequest, FleetWhatsAppResponse
from fleet.services.common import get_hire_or_404
from fleet.services.whatsapp_service import (
    ON_HIRE_WHATSAPP_BODY,
    normalize_uk_mobile,
    send_whatsapp,
    template_for,
)

router = APIRouter()


def _result_to_response(result: dict, to_number: str) -> FleetWhatsAppResponse:
    return FleetWhatsAppResponse(
        status="sent",
        provider=result.get("provider"),
        to=result.get("to") or to_number,
        sid=result.get("sid"),
        message_id=result.get("message_id"),
    )


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _money(value) -> str:
    raw = str(value or "").replace(",", "").replace("£", "").strip()
    try:
        return f"£{float(raw):.2f}"
    except (TypeError, ValueError):
        return raw or "the agreed amount"


def _first_name(full_name) -> str:
    return (str(full_name or "").strip().split(" ")[0]) or "there"


def _next_payment_day(payment_day) -> str:
    """The next occurrence of the hire's Payment Day, as dd/mm/yyyy."""
    name = str(payment_day or "").strip()
    if name not in WEEKDAYS:
        return "your payment day"
    target = WEEKDAYS.index(name)
    today = date.today()
    ahead = (target - today.weekday()) % 7 or 7
    return (today + timedelta(days=ahead)).strftime("%d/%m/%Y")


def _template_params(kind: str, hire) -> list:
    """Positional values for {{1}}, {{2}}… in the approved template.

    Built from the hire record rather than the screen, so an approved template
    can never be filled with values the record doesn't hold.
    """
    if kind == "reminder":
        return [
            _first_name(hire.driver_name),
            _money(hire.weekly_hire_payment),
            _next_payment_day(hire.payment_day),
        ]
    if kind == "price_rise":
        return [_first_name(hire.driver_name), _money(hire.weekly_hire_payment)]
    return []


def _send_hire_whatsapp(
    to_number: str, message: str, kind: str = "", hire=None,
) -> FleetWhatsAppResponse:
    body = (message or "").strip()
    template = template_for(kind)
    if not body and not template:
        raise HTTPException(status_code=400, detail="WhatsApp message is required.")

    normalised = normalize_uk_mobile(to_number)
    if not normalised:
        raise HTTPException(status_code=400, detail="A valid UK mobile number is required.")

    params = _template_params(kind, hire) if (template and hire is not None) else None
    result = send_whatsapp(normalised, body, kind=kind, params=params)
    if not result.get("sent"):
        raise HTTPException(status_code=502, detail=result.get("reason") or "WhatsApp message failed to send.")
    return _result_to_response(result, normalised)


@router.post("/hire/{hire_id}/whatsapp", response_model=FleetWhatsAppResponse)
def send_custom_whatsapp_route(
    hire_id: int,
    payload: FleetWhatsAppRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    to_number = payload.mobile or hire.driver_mobile or ""
    # Free-form text uses the message edited in the modal. When an approved
    # template is configured for this kind, WhatsApp sends the approved wording
    # instead and the edited text is ignored — templates cannot be altered.
    return _send_hire_whatsapp(to_number, payload.message, payload.kind or "", hire)


@router.post("/hire/{hire_id}/whatsapp/on-hire", response_model=FleetWhatsAppResponse)
def send_on_hire_whatsapp_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    return _send_hire_whatsapp(hire.driver_mobile or "", ON_HIRE_WHATSAPP_BODY, "on_hire", hire)
