from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import Optional
from appflow.models.total_loss import TotalLossIn, TotalLossOut
from appflow.services.total_loss_service import (
    create_total_loss,
    get_total_loss_by_claim,
    update_total_loss_by_claim,
    deactivate_total_loss_by_claim,
)
from libdata.settings import get_session

loss_router = APIRouter(prefix="/total-loss", tags=["Total Loss"])
from appflow.models.email_cta import EmailCTARequest
from appflow.services.repair_total_loss_email_service import (
    send_pav_to_client_email,
    send_engineer_report_to_tpi_email,
    instruct_fleet_off_hire_email,
)

@loss_router.post("/", response_model=TotalLossOut)
def create_total_loss_for_claim(total_loss_in: TotalLossIn,request: Request, db: Session = Depends(get_session)):
    return create_total_loss(db, total_loss_in,request)

@loss_router.get("/{claim_id}", response_model=TotalLossOut)
def get_total_loss_for_claim(claim_id: int, db: Session = Depends(get_session)):
    return get_total_loss_by_claim(db, claim_id)


@loss_router.put("/{claim_id}", response_model=TotalLossOut)
def update_total_loss_for_claim(claim_id: int, total_loss_in: TotalLossIn,request: Request, db: Session = Depends(get_session)):
    return update_total_loss_by_claim(db, claim_id, total_loss_in,request)


@loss_router.delete("/{claim_id}")
def deactivate_total_loss_for_claim(claim_id: int, db: Session = Depends(get_session)):
    return deactivate_total_loss_by_claim(db, claim_id)

@loss_router.post("/send-pav-client/{claim_id}")
def send_pav_client(
    claim_id: int,
    data: EmailCTARequest,
    request: Request,
    db: Session = Depends(get_session),
):
    return send_pav_to_client_email(db, claim_id, request, data.to_email)

@loss_router.post("/send-eng-report-tpi/{claim_id}")
def send_total_loss_eng_report_tpi(
    claim_id: int,
    data: EmailCTARequest,
    request: Request,
    db: Session = Depends(get_session),
):
    return send_engineer_report_to_tpi_email(db, claim_id, request, data.to_email)


@loss_router.post("/instruct-fleet-off-hire/{claim_id}")
def total_loss_instruct_fleet_off_hire(
    claim_id: int,
    data: EmailCTARequest,
    request: Request,
    db: Session = Depends(get_session),
):
    return instruct_fleet_off_hire_email(db, claim_id, request, data.to_email)