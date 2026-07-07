from typing import List
from fastapi import APIRouter, Depends, HTTPException,BackgroundTasks
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.utils import get_tenant_id,actor_id
from appflow.models.panel_solicitor import PanelSolicitorIn, PanelSolicitorOut,SolicitorEmailRequest,SolicitorAcceptedEmailRequest
from appflow.services.panel_solicitor_service import PanelSolicitorService,PanelSolicitorEmailService
from datetime import date

panel_solicitor_router = APIRouter(prefix="/panel-solicitors", tags=["Panel Solicitors"])


@panel_solicitor_router.get("/{claim_id}", response_model=PanelSolicitorOut)
def get_solicitor_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return PanelSolicitorService.get_solicitor_by_claim_id(claim_id, db)


@panel_solicitor_router.get("/company/{company_name}", response_model=PanelSolicitorOut)
def get_solicitor_by_company(company_name: str, db: Session = Depends(get_session)):
    return PanelSolicitorService.get_solicitor_by_company_name(company_name, db)


@panel_solicitor_router.post("/", response_model=PanelSolicitorOut)
def create_solicitor_route(
    solicitor: PanelSolicitorIn,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    current_user_id: int = Depends(actor_id),
    send_email: bool = False,
    send_acceptance_email: bool = False
):
    return PanelSolicitorService.create_solicitor(solicitor, db, tenant_id,current_user_id,send_email, send_acceptance_email)


@panel_solicitor_router.put("/{claim_id}", response_model=PanelSolicitorOut)
def update_solicitor_route(
    claim_id: int,
    solicitor: PanelSolicitorIn,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    current_user_id: int = Depends(actor_id),
    send_email: bool = False,
    send_acceptance_email: bool = False
):
    return PanelSolicitorService.update_solicitor(claim_id, solicitor, db, tenant_id,current_user_id,send_email, send_acceptance_email)


@panel_solicitor_router.patch("/{solicitor_id}")
def deactivate_solicitor_route(
    solicitor_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return PanelSolicitorService.deactivate_solicitor(solicitor_id, db, tenant_id)


@panel_solicitor_router.get("/search/{query}", response_model=List[PanelSolicitorOut])
def search_solicitors_route(
    query: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return PanelSolicitorService.search_solicitors(query, db, tenant_id)

@panel_solicitor_router.post("/send-email/{claim_id}")
def send_solicitor_email_route(
    claim_id: int,
    data: SolicitorEmailRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id)
):
    service = PanelSolicitorEmailService(db, tenant_id)
    background_tasks.add_task(
        service.send_email,
        claim_id=claim_id,
        solicitor_email=data.solicitor_email,
        company_name=data.company_name,
        current_user=current_user
    )
    return {"status": "success", "message": f"Email scheduled to {data.solicitor_email}"}


@panel_solicitor_router.post("/send-acceptance-email/{claim_id}")
def send_acceptance_email_route(
        claim_id: int,
        data: SolicitorAcceptedEmailRequest,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_session),
        current_user: int = Depends(actor_id),
        tenant_id: int = Depends(get_tenant_id)
):
    """
    Sends a 'Claim Accepted' email to the solicitor.
    """
    service = PanelSolicitorEmailService(db, tenant_id)
    recommendation_date = data.recommendation_date if hasattr(data, "recommendation_date") else date.today()

    background_tasks.add_task(
        service.send_acceptance_email,
        claim_id=claim_id,
        solicitor_email=data.solicitor_email,
        solicitor_name=data.company_name,  # use solicitor_name if available in your model
        recommendation_date=recommendation_date,
        current_user=current_user
    )
    return {"status": "success", "message": f"Acceptance email scheduled to {data.solicitor_email}"}
