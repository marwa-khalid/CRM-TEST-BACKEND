from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import FleetWhatsAppRequest, FleetWhatsAppResponse
from fleet.services.common import get_hire_or_404
from fleet.services.whatsapp_service import (
    ON_HIRE_WHATSAPP_BODY,
    normalize_uk_mobile,
    send_whatsapp,
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


def _send_hire_whatsapp(to_number: str, message: str) -> FleetWhatsAppResponse:
    body = (message or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="WhatsApp message is required.")

    normalised = normalize_uk_mobile(to_number)
    if not normalised:
        raise HTTPException(status_code=400, detail="A valid UK mobile number is required.")

    result = send_whatsapp(normalised, body)
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
    # The modal has both a phrase and a history/details textarea; send the final
    # editable message selected by the client.
    return _send_hire_whatsapp(to_number, payload.message)


@router.post("/hire/{hire_id}/whatsapp/on-hire", response_model=FleetWhatsAppResponse)
def send_on_hire_whatsapp_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    return _send_hire_whatsapp(hire.driver_mobile or "", ON_HIRE_WHATSAPP_BODY)
