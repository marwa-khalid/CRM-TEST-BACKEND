from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import List
from libdata.settings import get_session
from appflow.models.route_repair import RouteRepairCreate, RouteRepairOut
from appflow.services import route_repair_service as service

router = APIRouter(prefix="/route-repairs", tags=["Route Repairs"])
from appflow.models.email_cta import EmailCTARequest
from appflow.services.repair_total_loss_email_service import (
    send_cil_agreement_email,
    send_cil_to_client_email,
    send_engineer_report_to_tpi_email,
    instruct_fleet_off_hire_email,
)

@router.post("/", response_model=RouteRepairOut)
def create_route_repair(route_repair_in: RouteRepairCreate,request: Request, db: Session = Depends(get_session)):
    return service.create_route_repair(db, route_repair_in,request)

@router.get("/{claim_id}", response_model=RouteRepairOut)
def get_route_repairs_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return service.get_route_repairs_by_claim(db, claim_id)


@router.put("/{claim_id}", response_model=RouteRepairOut)
def update_route_repair_by_claim(claim_id: int, route_repair_in: RouteRepairCreate,request: Request, db: Session = Depends(get_session)):
    return service.update_route_repair_by_claim(db, claim_id, route_repair_in,request)


@router.delete("/{route-repair-id}")
def deactivate_route_repair(route_repair_id: int, db: Session = Depends(get_session)):
    return service.deactivate_route_repair(db, route_repair_id)


@router.post("/send-cil-agreement/{claim_id}")
def send_cil_agreement(
    claim_id: int,
    data: EmailCTARequest,
    request: Request,
    db: Session = Depends(get_session),
):
    return send_cil_agreement_email(db, claim_id, request, data.to_email)


@router.post("/send-cil-client/{claim_id}")
def send_cil_client(
    claim_id: int,
    data: EmailCTARequest,
    request: Request,
    db: Session = Depends(get_session),
):
    return send_cil_to_client_email(db, claim_id, request, data.to_email)


@router.post("/send-eng-report-tpi/{claim_id}")
def send_eng_report_tpi(
    claim_id: int,
    data: EmailCTARequest,
    request: Request,
    db: Session = Depends(get_session),
):
    return send_engineer_report_to_tpi_email(db, claim_id, request, data.to_email)


@router.post("/instruct-fleet-off-hire/{claim_id}")
def instruct_fleet_off_hire(
    claim_id: int,
    data: EmailCTARequest,
    request: Request,
    db: Session = Depends(get_session),
):
    return instruct_fleet_off_hire_email(db, claim_id, request, data.to_email)