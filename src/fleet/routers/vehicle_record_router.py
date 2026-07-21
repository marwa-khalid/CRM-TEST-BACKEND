from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from fleet.deps import actor_id, get_session, get_tenant_id
from fleet.models.schemas import (
    AppointmentPassedEmailRequest,
    LicensingAuthorityResponse,
    LicensingAuthorityUpdate,
    VehicleRecordResponse,
    VehicleRecordUpdate,
    VehicleServiceResponse,
    VehicleServiceUpdate,
)
from fleet.services import email_service as fleet_email_service
from fleet.services import (
    licensing_authority_service,
    vehicle_record_service,
    vehicle_sale_service,
    vehicle_service_record_service,
)

router = APIRouter()


@router.post("/vehicle-record", response_model=VehicleRecordResponse)
def create_vehicle_record_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    return vehicle_record_service.create_vehicle_record(db, tenant_id, actor)


@router.get("/vehicle-record", response_model=List[VehicleRecordResponse])
def list_vehicle_records_route(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return vehicle_record_service.list_vehicle_records(db, tenant_id)


@router.get("/vehicle-record/{record_id}", response_model=VehicleRecordResponse)
def get_vehicle_record_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return vehicle_record_service.get_vehicle_record(db, record_id, tenant_id)


@router.patch("/vehicle-record/{record_id}", response_model=VehicleRecordResponse)
def update_vehicle_record_route(
    record_id: int,
    payload: VehicleRecordUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    # exclude_unset so a field-level PATCH never blanks the fields it omits.
    return vehicle_record_service.update_vehicle_record(
        db, record_id, tenant_id, payload.model_dump(exclude_unset=True), actor,
    )


@router.delete("/vehicle-record/{record_id}")
def delete_vehicle_record_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    vehicle_record_service.delete_vehicle_record(db, record_id, tenant_id)
    return {"status": "deleted"}


# --------------------------------------------------------------------------- #
# The vehicle record is the Customer Side of a hire file — one per hire.
# --------------------------------------------------------------------------- #
@router.get("/hire/{hire_id}/vehicle-record", response_model=VehicleRecordResponse)
def get_hire_vehicle_record_route(
    hire_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    """Get (creating on first open) the vehicle record for this hire file."""
    return vehicle_record_service.get_or_create_for_hire(db, hire_id, tenant_id, actor)


@router.get("/vehicle-record/{record_id}/licensing-authority", response_model=List[LicensingAuthorityResponse])
def list_authorities_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return licensing_authority_service.list_authorities(db, record_id)


@router.post("/vehicle-record/{record_id}/licensing-authority", response_model=LicensingAuthorityResponse)
def create_authority_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return licensing_authority_service.create_authority(db, record_id, actor)


@router.patch("/vehicle-record/{record_id}/licensing-authority/{authority_id}", response_model=LicensingAuthorityResponse)
def update_authority_route(
    record_id: int,
    authority_id: int,
    payload: LicensingAuthorityUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return licensing_authority_service.update_authority(
        db, record_id, authority_id, payload.model_dump(exclude_unset=True), actor,
    )


@router.delete("/vehicle-record/{record_id}/licensing-authority/{authority_id}")
def delete_authority_route(
    record_id: int,
    authority_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    licensing_authority_service.delete_authority(db, record_id, authority_id)
    return {"status": "deleted"}


@router.post(
    "/vehicle-record/{record_id}/licensing-authority/{authority_id}/certificate/{kind}",
    response_model=LicensingAuthorityResponse,
)
def upload_certificate_route(
    record_id: int,
    authority_id: int,
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """kind = plating | mot."""
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return licensing_authority_service.upload_certificate(db, record_id, authority_id, kind, file)


@router.delete(
    "/vehicle-record/{record_id}/licensing-authority/{authority_id}/certificate/{kind}",
    response_model=LicensingAuthorityResponse,
)
def remove_certificate_route(
    record_id: int,
    authority_id: int,
    kind: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return licensing_authority_service.remove_certificate(db, record_id, authority_id, kind)


@router.get("/vehicle-record/{record_id}/licensing-letters/print-view", response_class=HTMLResponse)
def licensing_letters_print_view_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """One letter per licensing authority — preview, print, or print-to-PDF."""
    record = vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    authorities = licensing_authority_service.list_authorities(db, record_id)
    return HTMLResponse(licensing_authority_service.build_letters_html(db, record, authorities))


# --------------------------------------------------------------------------- #
# Servicing records — one per uploaded Service Invoice (the Service Summary Log)
# --------------------------------------------------------------------------- #
@router.get("/vehicle-record/{record_id}/service", response_model=List[VehicleServiceResponse])
def list_services_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return vehicle_service_record_service.list_services(db, record_id)


@router.post("/vehicle-record/{record_id}/service", response_model=VehicleServiceResponse)
def create_service_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return vehicle_service_record_service.create_service(db, record_id, actor)


@router.patch("/vehicle-record/{record_id}/service/{service_id}", response_model=VehicleServiceResponse)
def update_service_route(
    record_id: int,
    service_id: int,
    payload: VehicleServiceUpdate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor: int = Depends(actor_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return vehicle_service_record_service.update_service(
        db, record_id, service_id, payload.model_dump(exclude_unset=True), actor,
    )


@router.delete("/vehicle-record/{record_id}/service/{service_id}")
def delete_service_route(
    record_id: int,
    service_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    vehicle_service_record_service.delete_service(db, record_id, service_id)
    return {"status": "deleted"}


@router.post("/vehicle-record/{record_id}/service/{service_id}/invoice", response_model=VehicleServiceResponse)
def upload_service_invoice_route(
    record_id: int,
    service_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return vehicle_service_record_service.upload_invoice(db, record_id, service_id, file)


@router.get("/vehicle-record/{record_id}/sale-documents/print-view", response_class=HTMLResponse)
def sale_documents_print_view_route(
    record_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Release of Liability + Sale Receipt — preview, print, or print-to-PDF."""
    record = vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    return HTMLResponse(vehicle_sale_service.build_sale_documents_html(record))


def _uk_date(value) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


@router.post("/vehicle-record/{record_id}/licensing-authority/{authority_id}/email/{kind}")
def send_appointment_passed_email_route(
    record_id: int,
    authority_id: int,
    kind: str,
    payload: AppointmentPassedEmailRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """kind = plating | mot. Sends the appointment-passed confirmation."""
    if kind not in {"plating", "mot"}:
        raise HTTPException(status_code=400, detail="Unknown confirmation type.")

    record = vehicle_record_service.get_vehicle_record_or_404(db, record_id, tenant_id)
    authority = licensing_authority_service.get_authority_or_404(db, record_id, authority_id)
    registration = (record.registration_number or "").strip()

    if kind == "plating":
        data = {
            "registration": registration,
            "licensing_authority": authority.licensing_authority,
            "plate_number": authority.plate_number,
            "plating_start": _uk_date(authority.plating_start_date),
            "plating_expiry": _uk_date(authority.plating_expiry_date),
        }
        result = fleet_email_service.send_plating_passed_email(
            to=payload.to or fleet_email_service.FLEET_INBOX,
            subject=payload.subject or "",
            data=data,
            cc=payload.cc,
        )
    else:
        data = {
            "registration": registration,
            "mot_centre_name": authority.mot_centre_name,
            "last_mot": _uk_date(authority.last_mot_date),
            "mot_expiry": _uk_date(authority.mot_expiry_date),
        }
        result = fleet_email_service.send_mot_passed_email(
            to=payload.to or fleet_email_service.FLEET_INBOX,
            subject=payload.subject or "",
            data=data,
            cc=payload.cc,
        )

    if isinstance(result, dict) and result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("detail") or "Email could not be sent.")
    return {"status": "sent", "to": payload.to or fleet_email_service.FLEET_INBOX}
