from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException,UploadFile,File, Request
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.utils import get_tenant_id
from appflow.models.engineer_detail import (
    EngineerDetailCreate,
    EngineerDetailOut,EngineerEmailRequest
)
from fastapi.responses import JSONResponse

from appflow.services.engineer_detail_service import EngineerDetailService
from appflow.services.import_job_service import import_job_service
from appflow.services.import_utils import serialize_uploads
from appflow.services.import_workers import run_engineer_detail_import
from appflow.services.engineer_email_service import send_engineer_instruction_email
from appflow.utils import actor_id
from appflow.services.ocr_engineer_service import engineer_ocr_service, process_engineer_detail
engineer_router = APIRouter(prefix="/engineer-details", tags=["Engineer Details"])


def _notify_engineer_report(db, claim_id, tenant_id, actor_id):
    """(#5) Engineer report saved/updated -> notify the actor."""
    if not claim_id:
        return
    try:
        from appflow.services.notification_service import safe_notify
        from appflow.utils import build_case_reference
        ref = build_case_reference(claim_id, db)
        safe_notify(
            db, recipient_user_id=actor_id, tenant_id=tenant_id, actor_user_id=actor_id,
            category="Claim", tab="Claims", title="Engineer Report Uploaded",
            description=f"Engineer report updated for {ref}.", claim_id=claim_id,
        )
    except Exception:
        pass

# ======================= ENGINEER DETAILS =======================

@engineer_router.get("/{claim_id}", response_model=EngineerDetailOut)
def get_engineer_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return EngineerDetailService.get_engineer_by_claim_id(claim_id, db)


@engineer_router.get("/company/{company_name}", response_model=EngineerDetailOut)
def get_engineer_by_company(company_name: str, db: Session = Depends(get_session)):
    return EngineerDetailService.get_engineer_by_company_name(company_name, db)


@engineer_router.post("/", response_model=EngineerDetailOut)
def create_engineer_route(
    engineer: EngineerDetailCreate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor_id: int = Depends(actor_id)
):
    result = EngineerDetailService.create_engineer(engineer, db, tenant_id, actor_id)
    # Notification now fires inside the service, only when the report is actually
    # received (uploaded) — not on every save.
    return result


@engineer_router.put("/{claim_id}", response_model=EngineerDetailOut)
def update_engineer_route(
    claim_id: int,
    engineer: EngineerDetailCreate,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    actor_id: int = Depends(actor_id)
):
    result = EngineerDetailService.update_engineer(claim_id, engineer, db, tenant_id, actor_id)
    # Notification now fires inside the service, only when the report is actually
    # received (uploaded) — not on every value change.
    return result


@engineer_router.patch("/{engineer_id}")
def deactivate_engineer_route(
    engineer_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return EngineerDetailService.deactivate_engineer(engineer_id, db, tenant_id)

@engineer_router.get("/search/{query}", response_model=List[EngineerDetailOut])
def search_engineers_route(
    query: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return EngineerDetailService.search_engineers(query, db, tenant_id)


@engineer_router.get("/companies/search/{query}")
def search_engineer_companies_route(
    query: str,
    db: Session = Depends(get_session),
):
    """Company Name autocomplete for the Engineer Details screen (name + address)."""
    return EngineerDetailService.search_engineer_companies(query, db)

@engineer_router.post("/import-engineer-detail/", status_code=202)
async def import_engineer_detail(
    claim_id:int,
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
       db: Session = Depends(get_session)
):
    actor = actor_id(request)
    tenant_id = get_tenant_id(request)
    print(files)
    engineer_report_details= process_engineer_detail(files,db,engineer_ocr_service,claim_id,actor,tenant_id)
    # background_tasks.add_task(run_engineer_detail_import, job.id, payloads, claim_id, actor,tenant)
    return JSONResponse(content={"engineer_report_details": engineer_report_details}, status_code=200)


@engineer_router.post("/send-instruction/{claim_id}")
def send_instruction(
        claim_id: int,
        data:EngineerEmailRequest,
        db: Session = Depends(get_session),
        current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)
):
    """
    Endpoint to send instructing engineer email with attached .doc file populated with claim data.
    """
    return send_engineer_instruction_email(
        claim_id=claim_id,
        data=data,
        db=db,current_user=current_user,tenant_id=tenant_id
    )