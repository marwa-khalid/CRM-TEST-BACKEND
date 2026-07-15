from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.models.schemas import FleetSmsRequest, FleetSmsResponse
from fleet.services.common import get_hire_or_404
from fleet.services.sms_service import ON_HIRE_SMS_BODY, normalize_uk_mobile, send_sms

router = APIRouter()


def _result_to_response(result: dict, to_number: str) -> FleetSmsResponse:
    return FleetSmsResponse(
        status="sent",
        provider=result.get("provider"),
        to=result.get("to") or to_number,
        sid=result.get("sid"),
        message_id=result.get("message_id"),
    )


def _send_hire_sms(to_number: str, message: str) -> FleetSmsResponse:
    body = (message or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="SMS message is required.")

    normalised = normalize_uk_mobile(to_number)
    if not normalised:
        raise HTTPException(status_code=400, detail="A valid UK mobile number is required.")

    result = send_sms(normalised, body)
    if not result.get("sent"):
        raise HTTPException(status_code=502, detail=result.get("reason") or "SMS failed to send.")
    return _result_to_response(result, normalised)


@router.post("/hire/{hire_id}/sms", response_model=FleetSmsResponse)
def send_custom_sms_route(
    hire_id: int,
    payload: FleetSmsRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    to_number = payload.mobile or hire.driver_mobile or ""
    # The modal has both a phrase and a history/details textarea; send the final
    # editable message selected by the client.
    return _send_hire_sms(to_number, payload.message)


@router.post("/hire/{hire_id}/sms/on-hire", response_model=FleetSmsResponse)
def send_on_hire_sms_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    hire = get_hire_or_404(db, hire_id, tenant_id)
    return _send_hire_sms(hire.driver_mobile or "", ON_HIRE_SMS_BODY)
