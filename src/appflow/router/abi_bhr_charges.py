from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional

from libdata.settings import get_session
from libdata.models.tables import User
from appflow.models.abi_bhr_charges import ABIBHRChargesIn, ABIBHRChargesOut
from appflow.services.abi_bhr_charges_service import ABIBHRChargesService
from appflow.services.payment_pack_service import generate_payment_pack
from appflow.services.payment_pack_email_service import send_payment_pack_email
from appflow.utils import actor_id, get_tenant_id

abi_bhr_charges_router = APIRouter(prefix="/abi-bhr-charges", tags=["ABI & BHR Charges"])


@abi_bhr_charges_router.get("/{claim_id}", response_model=Optional[ABIBHRChargesOut])
def get_abi_bhr_charges(claim_id: int, db: Session = Depends(get_session)):
    return ABIBHRChargesService.get_by_claim(claim_id, db)


@abi_bhr_charges_router.post("/", response_model=ABIBHRChargesOut)
def save_abi_bhr_charges(
    payload: ABIBHRChargesIn,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    return ABIBHRChargesService.save(payload, db, current_user)


@abi_bhr_charges_router.post("/payment-pack/{claim_id}")
def generate_payment_pack_endpoint(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    try:
        tenant_id = get_tenant_id(request)
        # Sign-off name = logged-in user's email local-part (before the @)
        sign_off_name = ""
        user = db.query(User).filter(User.id == current_user).first() if current_user else None
        if user and user.user_name:
            sign_off_name = user.user_name.split("@")[0]
        zip_bytes, filename = generate_payment_pack(claim_id, tenant_id, db, sign_off_name)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@abi_bhr_charges_router.post("/payment-pack/{claim_id}/send-email")
async def send_payment_pack_email_endpoint(
    claim_id: int,
    request: Request,
    to_email: str = Form(...),
    cc_email: str | None = Form(None),
    subject: str | None = Form(None),
    body: str | None = Form(None),
    document_name: str | None = Form(None),
    attachment: UploadFile = File(...),
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    try:
        attachment_bytes = await attachment.read()
        return send_payment_pack_email(
            db=db,
            claim_id=claim_id,
            tenant_id=get_tenant_id(request),
            current_user=current_user,
            to_email=to_email,
            cc_email=cc_email,
            subject=subject,
            body=body,
            attachment_bytes=attachment_bytes,
            attachment_name=document_name or attachment.filename or "Payment-Pack.pdf",
            attachment_content_type=attachment.content_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
