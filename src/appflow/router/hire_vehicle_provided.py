from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from appflow.services.hire_vehicle_provided_service import HireVehicleProvidedService
from appflow.models.hire_vehicle_provides import (
    HireVehicleProvidedIn,
    HireVehicleProvidedOut, SectionBVehicleOut,HireVehicleProvidedUpdateIn
)
from appflow.utils import actor_id
from libdata.settings import get_session
from appflow.utils import get_tenant_id
from sendgrid import SendGridAPIClient
from libdata.models.tables import ClientDetail, Address
import base64
import os
from datetime import datetime
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId
from pydantic import BaseModel

class Msg(BaseModel):
    detail: str
    
hire_vehicle_provided_router = APIRouter(
    prefix="/hire-vehicle-provided",
    tags=["Hire Vehicle Provided"]
)


@hire_vehicle_provided_router.post("/", response_model=List[HireVehicleProvidedOut])
def create_hire_vehicle_provided(
        payload: HireVehicleProvidedIn,
        db: Session = Depends(get_session),
        current_user=Depends(actor_id),
        tenant_id = Depends(get_tenant_id),
        switch_vehicle: bool = Query(False, description="If true, include previous vehicle info in email")
):
    """Create Hire Vehicle Provided (single Section A + multiple Section B records)"""
    return HireVehicleProvidedService.create_hire_vehicle_provided(payload, db, current_user,tenant_id,switch_vehicle)


@hire_vehicle_provided_router.put("/{claim_id}", response_model=List[HireVehicleProvidedOut])
def update_hire_vehicle_provided(
        claim_id: int,
        payload: HireVehicleProvidedUpdateIn,
        db: Session = Depends(get_session),
        current_user=Depends(actor_id),
        tenant_id = Depends(get_tenant_id),
        switch_vehicle: bool = Query(False, description="If true, include previous vehicle info in email")
):
    """Update Hire Vehicle Provided by claim_id"""
    return HireVehicleProvidedService.update_hire_vehicle_provided_by_claim_id(claim_id, payload, db, current_user,tenant_id,switch_vehicle)


@hire_vehicle_provided_router.get("/{claim_id}", response_model=List[HireVehicleProvidedOut])
def get_hire_vehicle_provided_by_claim_id(
        claim_id: int,
        db: Session = Depends(get_session),
        current_user=Depends(actor_id),
):
    """Get Hire Vehicle Provided records by claim_id"""
    return HireVehicleProvidedService.get_hire_vehicle_provided_by_claim_id(claim_id, db, current_user)


@hire_vehicle_provided_router.put("/{claim_id}/deactivate")
def deactivate_hire_vehicle_provided(
        claim_id: int,
        db: Session = Depends(get_session),
        current_user=Depends(actor_id),
):
    """Deactivate Hire Vehicle Provided record"""
    return HireVehicleProvidedService.deactivate_hire_vehicle_provided(claim_id, db, current_user)


@hire_vehicle_provided_router.get("/section-b/{claim_id}", response_model=list[SectionBVehicleOut])
def get_section_b_vehicles(
        claim_id: int,
        db: Session = Depends(get_session),
):
    """Fetch make, model, registration, start/end date for Section B vehicles by claim_id."""
    return HireVehicleProvidedService.get_section_b_vehicle_details(claim_id, db)


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
TEMPLATE_DIR = os.path.join(BASE_DIR, "appflow", "templates")

@hire_vehicle_provided_router.get("/download-fee-exemption-form/{claim_id}")
def download_fee_exemption_form(
    claim_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
    tenant =Depends(get_tenant_id)
):

    return HireVehicleProvidedService.download_fee_exemption_form(claim_id, db,current_user,tenant)

@hire_vehicle_provided_router.post("/send-fee-exemption-email")
def send_fee_exemption_email(
    claim_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
):

    return HireVehicleProvidedService.send_fee_exemption_email(claim_id=claim_id, db=db)

@hire_vehicle_provided_router.post("/send-hire-documentation-agreement/{claim_id}")
def send_hire_documentation_agreement_email(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return HireVehicleProvidedService.send_hire_documentation_agreement_xlsx(claim_id=claim_id, db=db)

@hire_vehicle_provided_router.post("/send-storage-recovery/{claim_id}")
def send_storage_recovery_email(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return HireVehicleProvidedService.send_storage_recovery_xlsx(claim_id=claim_id, db=db)

@hire_vehicle_provided_router.post("/send-mitigation-questionnaire/{claim_id}")
def send_mitigation_questionnaire_email(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return HireVehicleProvidedService.send_mitigation_questionnaire_xlsx(claim_id=claim_id, db=db)

@hire_vehicle_provided_router.post("/send-vehicle-check-sheet/{claim_id}")
def send_vehicle_check_sheet_email(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return HireVehicleProvidedService.send_vehicle_check_sheet_xlsx(claim_id=claim_id, db=db)

@hire_vehicle_provided_router.get("/claim-summary/{claim_id}")
def get_instruction_fleet_summary(
    claim_id: int,
    on_hire: bool = False,
    off_hire: bool = False,
    send_fee_exemption_form: bool = False,
    hire_documentation_agreement: bool = False,
    storage_recovery: bool = False,
    mitigation_questionnaire: bool = False,
    vehicle_check_sheet: bool = False,
    db: Session = Depends(get_session)
):
    return HireVehicleProvidedService.get_instruct_fleet_summary(
        claim_id, db,
        on_hire=on_hire,
        off_hire=off_hire,
        send_fee_exemption_form=send_fee_exemption_form,
        hire_documentation_agreement=hire_documentation_agreement,
        storage_recovery=storage_recovery,
        vehicle_check_sheet=vehicle_check_sheet,
        mitigation_questionnaire=mitigation_questionnaire,
    )


@hire_vehicle_provided_router.get("/download-hire-documentation-agreement/{claim_id}")
def download_hire_documentation_agreement_xlsx(
    claim_id: int,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)
):
    return HireVehicleProvidedService.download_hire_documentation_agreement_xlsx(claim_id=claim_id, db=db,current_user=current_user,tenant_id=tenant_id)

@hire_vehicle_provided_router.get("/download-storage-recovery/{claim_id}")
def download_storage_recovery_xlsx(
    claim_id: int,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)
):
    return HireVehicleProvidedService.download_storage_recovery_xlsx(claim_id=claim_id, db=db,current_user=current_user,tenant_id=tenant_id)

@hire_vehicle_provided_router.get("/download-mitigation-questionnaire/{claim_id}")
def download_mitigation_questionnaire_xlsx(
    claim_id: int,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)
):
    return HireVehicleProvidedService.download_mitigation_questionnaire_xlsx(
        claim_id=claim_id,
        db=db,current_user=current_user,tenant_id=tenant_id
    )

@hire_vehicle_provided_router.get("/download-vehicle-check-sheet/{claim_id}")
def download_vehicle_check_sheet_xlsx(
    claim_id: int,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)
):
    return HireVehicleProvidedService.download_vehicle_check_sheet_xlsx(
        claim_id=claim_id,
        db=db,current_user=current_user,tenant_id=tenant_id
    )

@hire_vehicle_provided_router.post("/inst-to-off-hire", response_model=Msg)
def off_hire_mail_route(payload: dict):
    result = HireVehicleProvidedService.process_off_hire_instruction(payload)
    
    if result and (result.status_code == 200 or result.status_code == 202):
        return {"detail": "Instruction email sent successfully","result":result}
    
    raise HTTPException(status_code=500, detail="Failed to send email")

@hire_vehicle_provided_router.post("/inst-to-on-hire", response_model=Msg)
def on_hire_mail_route(payload: dict):
    result = HireVehicleProvidedService.process_on_hire_instruction(payload)
    
    if result and (result.status_code == 200 or result.status_code == 202):
        return {"detail": "Instruction email sent successfully","result":result}
    
    raise HTTPException(status_code=500, detail="Failed to send email")