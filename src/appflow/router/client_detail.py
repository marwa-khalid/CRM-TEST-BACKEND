from fastapi import APIRouter, Depends, HTTPException, Request, Path
from sqlalchemy.orm import Session
from typing import List

from libdata.settings import get_session
from appflow.models.client_detail import ClientDetailIn, ClientDetailOut
from appflow.services.client_service import (
    create_client_service,
    list_clients_service,
    get_client_service,
    update_client_service,
    deactivate_client_service,prepare_cil_agreement_letter,prepare_send_cil_to_client,get_static_doc,send_vulnerable_notify_manager,build_vulnerable_email_data
)

from appflow.services.client_service import get_client_by_claim_id
from libdata.enums import PersonRoleEnum,HistoryLogType
from io import BytesIO
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
from appflow.utils import get_tenant_id,actor_id,build_case_reference
from appflow.services.history_activity_service import HistoryActivityService

client_router = APIRouter(prefix="/clients", tags=["Clients"])


@client_router.post("/", response_model=ClientDetailOut)
def create_client(
    request: Request, client: ClientDetailIn, db: Session = Depends(get_session)
):
    return create_client_service(request, client, db, role=PersonRoleEnum.CLIENT)


@client_router.get("/", response_model=List[ClientDetailOut])
def list_clients(request: Request, db: Session = Depends(get_session)):
    return list_clients_service(request, db, role=PersonRoleEnum.CLIENT)

@client_router.get("/preview-vulnerable-notify")
def preview_vulnerable_notify(
    claim_id: int,
    db: Session = Depends(get_session)
):
    data = build_vulnerable_email_data(claim_id, db)
    return {
        "data": data
    }

@client_router.get("/{client_id}", response_model=ClientDetailOut)
def get_client(client_id: int, request: Request, db: Session = Depends(get_session)):
    return get_client_service(client_id, request, db, role=PersonRoleEnum.CLIENT)


@client_router.get("/claim/{claim_id}", response_model=ClientDetailOut)
def get_client_by_claim(claim_id: int, request: Request, db: Session = Depends(get_session)):
    return get_client_by_claim_id(claim_id, request, db, role=PersonRoleEnum.CLIENT)


@client_router.put("/{claim_id}", response_model=ClientDetailOut)
def update_client(
    claim_id: int,
    request: Request,
    client_data: ClientDetailIn,
    db: Session = Depends(get_session)
):
    return update_client_service(claim_id, request, client_data, db, role=PersonRoleEnum.CLIENT)


@client_router.delete("/{claim_id}")
def deactivate_client(claim_id: int, request: Request, db: Session = Depends(get_session)):
    return deactivate_client_service(claim_id, request, db, role=PersonRoleEnum.CLIENT)

@client_router.get("/download-cil-agreement-letter/{claim_id}")
def download_cil_agreement_letter(claim_id: int, db: Session = Depends(get_session),current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)):
    """
    Generate engineer instruction DOCX and return it as a downloadable file.
    """
    doc_bytes = prepare_cil_agreement_letter(claim_id, db)
    buffer = BytesIO(doc_bytes)
    reference = build_case_reference(claim_id,db)
    HistoryActivityService.create_activity(
        db=db,
        claim_id=claim_id,
        file_name=f"The cil agreement letter downloaded for claim {reference}",
        file_path="",
        file_type=HistoryLogType.DOWNLOAD_CIL_LETTER,
        user_id=current_user,
        tenant_id=tenant_id
    )

    headers = {
        "Content-Disposition": f'attachment; filename="CIL_Agreement_Letter_{reference}.docx"'
    }

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers
    )

@client_router.get("/download-send-cil-to-client/{claim_id}")
def download_send_cil_to_client(claim_id: int, db: Session = Depends(get_session),current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)):
    """
    Generate engineer instruction DOCX and return it as a downloadable file.
    """
    doc_bytes = prepare_send_cil_to_client(claim_id, db)
    buffer = BytesIO(doc_bytes)
    reference = build_case_reference(claim_id,db)
    HistoryActivityService.create_activity(
        db=db,
        claim_id=claim_id,
        file_name=f"The sent cil to client document downloaded for claim {reference}",
        file_path="",
        file_type=HistoryLogType.DOWNLOAD_CIL_CLIENT,
        user_id=current_user,
        tenant_id=tenant_id
    )

    headers = {
        "Content-Disposition": f'attachment; filename="CIL_TO_CLIENT_{reference}.docx"'
    }

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers
    )

@client_router.get("/download-vulnerable-persons-policy-doc/{claim_id}")
def download_vulnerable_persons_policy_doc(claim_id: int,db: Session = Depends(get_session),current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)):
    """
    Download a predefined DOCX file (vulnerable.docx) for a given claim ID.
    """
    file_path = get_static_doc(claim_id, "vulnerable_persons_policy.docx")
    reference = build_case_reference(claim_id,db)
    HistoryActivityService.create_activity(
        db=db,
        claim_id=claim_id,
        file_name=f"Vulnerable Persons Policy Document Downloaded For Claim {reference}",
        file_path="",
        file_type=HistoryLogType.DOWNLOAD_VULNERABLE_POLICY,
        user_id=current_user,
        tenant_id=tenant_id
    )

    return FileResponse(
        path=file_path,
        filename=f"Vulnerable_persons_policy_{reference}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@client_router.post("/send-vulnerable-notify")
def send_vulnerable_notify(
    claim_id: int,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id), tenant_id: int = Depends(get_tenant_id)
):
    return send_vulnerable_notify_manager(claim_id=claim_id, db=db,current_user=current_user,tenant_id=tenant_id)