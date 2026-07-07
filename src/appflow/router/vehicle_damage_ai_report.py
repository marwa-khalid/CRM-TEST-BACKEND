import json
from fastapi import APIRouter, Depends, File, Form, Body, UploadFile, status
from sqlalchemy.orm import Session

from libdata.settings import get_session
from appflow.models.vehicle_detail import (
    VehicleDamageAIReportLatestOut,
    VehicleDamageReportSyncOut,
)
from appflow.services.vehicle_damage_ai_report_service import VehicleDamageAIReportService
from appflow.utils import actor_id
from appflow.services.roboflow_service import roboflow_service


vehicle_damage_report_router = APIRouter(
    prefix="/vehicle-damage-reports",
    tags=["Vehicle Damage AI Reports"],
)

@vehicle_damage_report_router.post(
    "/reports",
    status_code=status.HTTP_200_OK,
)
def save_vehicle_damage_report(
    payload: dict = Body(...),
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
):
    result = VehicleDamageAIReportService.save_or_update_analysis_payload(
        payload=payload,
        db=db,
        user_id=user_id,
    )
    # (#6) AI damage detection completed -> notify the actor.
    try:
        from appflow.services.notification_service import safe_notify
        cid = payload.get("claim_id") if isinstance(payload, dict) else None
        safe_notify(
            db, recipient_user_id=user_id, actor_user_id=user_id,
            category="Claim", tab="Claims", title="AI Damage Detection Completed",
            description="AI vehicle damage analysis has completed.", claim_id=cid,
        )
    except Exception:
        pass
    return result

@vehicle_damage_report_router.get(
    "/claim/{claim_id}/latest",
    response_model=VehicleDamageAIReportLatestOut,
    status_code=status.HTTP_200_OK,
)
def get_latest_vehicle_damage_report(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return VehicleDamageAIReportService.get_latest_by_claim(claim_id, db)

from fastapi import APIRouter, UploadFile, File, Form
from typing import List
from appflow.utils import get_tenant_id,actor_id,build_case_reference

@vehicle_damage_report_router.post("/analyze")
async def analyze_vehicle_damage(
    claim_id: int = Form(...),
    assessment_type: str = Form("Client vehicle only"),
    images: List[UploadFile] = File(None),
    # Dedicated third-party image set, used when assessment_type is "Both" (the
    # `images` field then carries the client vehicle's images). Each set is
    # tagged with its vehicle_type so the report/slider can switch between them.
    third_party_images: List[UploadFile] = File(None),
    # JSON array of the current report's already-analyzed images; when present we
    # only OCR the newly uploaded `images` and merge these in (no re-analysis).
    existing_images: str = Form(None),
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
    tenant_id:int= Depends(get_tenant_id)
):
    parsed_existing = None
    if existing_images:
        try:
            parsed_existing = json.loads(existing_images)
        except (ValueError, TypeError):
            parsed_existing = None

    return await VehicleDamageAIReportService.analyze_and_store(
        claim_id=claim_id,
        assessment_type=assessment_type,
        images=images,
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
        existing_images=parsed_existing,
        third_party_images=third_party_images,
    )

@vehicle_damage_report_router.post(
    "/save-adjustments",
    status_code=status.HTTP_200_OK,
)
def save_manual_adjustments(
    payload: dict = Body(...),
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
):
    """Save the handler's manual adjustments and regenerate the AI report PDF on
    the server (ReportLab). Body: { claim_id, decisions, notes, vehicleStatus }."""
    manual_adjustments = {
        "decisions": payload.get("decisions") or {},
        "notes": payload.get("notes") or "",
        "vehicleStatus": payload.get("vehicleStatus") or payload.get("vehicle_status") or "Roadworthy",
    }
    return VehicleDamageAIReportService.regenerate_pdf_with_adjustments(
        claim_id=payload.get("claim_id"),
        manual_adjustments=manual_adjustments,
        db=db,
        user_id=user_id,
    )

@vehicle_damage_report_router.post(
    "/sync-pdf",
    response_model=VehicleDamageReportSyncOut,
    status_code=status.HTTP_200_OK,
)
def sync_vehicle_damage_report_pdf(
    claim_id: int = Form(...),
    file: UploadFile = File(...),
    report_payload: str = Form(...),
    db: Session = Depends(get_session),
    user_id: int = Depends(actor_id),
):
    return VehicleDamageAIReportService.sync_pdf_and_payload(
        claim_id=claim_id,
        file=file,
        report_payload=report_payload,
        db=db,
        user_id=user_id,
    )
