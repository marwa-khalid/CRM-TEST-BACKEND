from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from libdata.settings import get_session
from appflow.models.vehicle_detail import (
    ClientVehicleCreate, ClientVehicleResponse, VehicleDamageBatchUpdate,
    VehicleDamageAIUpdate, VehicleDamageAIReportIn, VehicleDamageAIReportOut,
    ComprehensiveVehicleDamageReport
)
from appflow.models.vehicle_damage_report_email import DamageReportEmailRequest, DamageReportEmailResponse
from appflow.services.vehicle_detail import ( create_client_vehicle,get_client_vehicle,list_client_vehicles,
update_client_vehicle,deactivate_client_vehicle,update_vehicle_damage,create_ai_damage_report,save_ai_images,
get_comprehensive_vehicle_damage_report
                                              )
from appflow.services.vehicle_damage_report_email_service import VehicleDamageReportEmailService
from appflow.utils import get_tenant_id, get_full_url
from fastapi.responses import JSONResponse
from appflow.services.import_job_service import import_job_service
from appflow.services.import_utils import serialize_uploads
from appflow.services.import_workers import run_client_vehicle_import
from appflow.utils import actor_id
from appflow.services.vehicle_upload_service import process_client_vehicle
from appflow.services.ocr_Service import ocr_service

vehicle_router = APIRouter(prefix="/client-vehicles", tags=["Client Vehicles"])


@vehicle_router.post("/", response_model=ClientVehicleResponse)
def create_client_vehicle_router(vehicle: ClientVehicleCreate,request: Request, db: Session = Depends(get_session)):
    return create_client_vehicle(vehicle, db,request)


@vehicle_router.get("/{claim_id}", response_model=ClientVehicleResponse)
def get_client_vehicle_router(claim_id: int, db: Session = Depends(get_session)):
    return get_client_vehicle(claim_id, db)


@vehicle_router.get("/claim/{claim_id}", response_model=List[ClientVehicleResponse])
def list_client_vehicles_router(claim_id: int, db: Session = Depends(get_session)):
    return list_client_vehicles(claim_id, db)


@vehicle_router.put("/damage-update", summary="Update manual vehicle damage fields")
def update_vehicle_damage_router(payload: VehicleDamageBatchUpdate, db: Session = Depends(get_session)):
    return update_vehicle_damage(payload, db)


@vehicle_router.put("/{claim_id}", response_model=ClientVehicleResponse)
def update_client_vehicle_router(claim_id: int, vehicle: ClientVehicleCreate,request: Request, db: Session = Depends(get_session)):
    return update_client_vehicle(claim_id,vehicle, db,request)


@vehicle_router.put("/{vehicle_id}")
def deactivate_client_vehicle_router(vehicle_id: int, db: Session = Depends(get_session)):
    return deactivate_client_vehicle(vehicle_id, db)


@vehicle_router.post("/damage/ai", response_model=list[VehicleDamageAIReportOut])
async def create_ai_damage_report_router(
    body: VehicleDamageAIReportIn, 
    request: Request,
    db: Session = Depends(get_session)
):
    """
    Create AI damage reports for client and/or third-party vehicles with automatic versioning.

    - First upload: Creates Version 1
    - Second upload: Creates Version 2 and supersedes V1
    - Third upload: Creates Version 3 and supersedes V2
    - Works for both client and third-party vehicles independently
    """
    try:
        # Get tenant_id and user_id for versioning
        tenant_id = get_tenant_id(request)
        user_id = actor_id(request)
        
        # Use image paths from the payload
        image_paths = body.images or []
        
        # Create AI reports for both vehicles (with versioning)
        reports = create_ai_damage_report(body, image_paths, db, tenant_id, user_id)
        return reports
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating AI damage report: {str(e)}")


@vehicle_router.post("/import_client_vehicle/")
async def import_client_vehicle( 
    claim_id: int,
    request:Request,files: list[UploadFile] = File(...), db: Session = Depends(get_session)):
    # Call import_client_vehicle function, passing only the required arguments
    actor = actor_id(request)
    print(claim_id)
    tenant_id = get_tenant_id(request)
    print(actor)
    print(tenant_id)
    vehicle_details = process_client_vehicle(files, db, ocr_service,claim_id, actor,tenant_id)

    return JSONResponse(content={"client_vehicle_detail": vehicle_details}, status_code=200)
@vehicle_router.get("/damage-report/{claim_id}/client", response_model=Dict[str, Any])
def get_client_vehicle_damage_report_router(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    """
    Get client vehicle damage report in Roboflow-like response structure
    """
    try:
        # Fetch client vehicle ID from database based on claim_id
        from libdata.models.tables import VehicleDetail
        client_vehicle = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
        if not client_vehicle:
            raise HTTPException(status_code=404, detail=f"No client vehicle found for claim {claim_id}")
        
        client_vehicle_id = client_vehicle.id
        
        tenant_id = get_tenant_id(request)
        svc = VehicleDamageReportEmailService(db, tenant_id)
        rpt = svc._compose_report_for_client_vehicle(claim_id, client_vehicle_id)

        # Build normalized_report similar to /car-damage-detection/detect
        dd = rpt.detected_damages
        confidence_percent = dd.confidence_percent or 0
        if confidence_percent >= 80:
            confidence_bucket = "high"
        elif confidence_percent >= 60:
            confidence_bucket = "medium"
        else:
            confidence_bucket = "low"

        normalized_report = {
            "client_area_of_damage": rpt.vehicle_details and dd.area_of_damage or "",
            "client_unrelated_damage": rpt.client_unrelated_damage or "",
            "client_vehicle_status_id": None,
            "damage_diagram": {
                "ai_analysis": "comprehensive",
                "confidence": confidence_bucket,
                "detected_areas": [x.strip() for x in (dd.area_of_damage or "").split(",") if x.strip()],
                "detected_types": [x.strip() for x in (dd.type_of_damage or "").split(",") if x.strip()],
            },
            "damage_side": dd.damage_side or "",
            "area_of_damage": dd.area_of_damage or "",
            "type_of_damage": dd.type_of_damage or "",
            "severity": dd.severity or "",
            "confidence_percent": confidence_percent,
            "total_damaged_points_identified": dd.total_damaged_points_identified or 0,
            "suggested_repair_action": dd.ai_suggested_actions or "",
            "vehicle_status_id": None,
            "raw_result": {
                "summary": rpt.summary.dict() if hasattr(rpt.summary, "dict") else rpt.summary,
            },
        }

        images = [
            {"file_path": get_full_url(img.file_path), "original_filename": img.original_filename}
            for img in rpt.uploaded_images
        ] if rpt.uploaded_images else []

        response: Dict[str, Any] = {
            "predictions": {},
            "summary": {
                "total_detections": dd.total_damaged_points_identified or 0,
                "average_confidence": (confidence_percent or 0) / 100.0,
            },
            "metadata": {
                "report_id": rpt.report_details.report_id,
                "claim_id": rpt.report_details.claim_id,
                "client_vehicle_id": client_vehicle_id,
                "generated_on": rpt.report_details.generated_on,
            },
            "normalized_report": normalized_report,
            "images": images,
            # Vehicle details
            "vehicle_details": {
                "vehicle_reg_no": rpt.vehicle_details.vehicle_reg_no,
                "make_model": rpt.vehicle_details.make_model,
                "color": rpt.vehicle_details.color,
                "year": rpt.vehicle_details.year,
            } if rpt.vehicle_details else None,
            # Upload/Created by details
            "upload_details": {
                "uploaded_by": rpt.upload_details.uploaded_by,
                "file_name": rpt.upload_details.file_name,
                "uploaded_on": rpt.upload_details.uploaded_on,
                "source": rpt.upload_details.source,
            } if rpt.upload_details else None,
        }

        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating client vehicle damage report: {str(e)}")


@vehicle_router.get("/damage-report/{claim_id}/third-party", response_model=Dict[str, Any])
def get_third_party_vehicle_damage_report_router(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    """
    Get third-party vehicle damage report in Roboflow-like response structure
    """
    try:
        # Fetch third-party vehicle ID from database based on claim_id
        from libdata.models.tables import VehicleDetail, ThirdPartyVehicle
        client_vehicle = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
        if not client_vehicle:
            raise HTTPException(status_code=404, detail=f"No client vehicle found for claim {claim_id}")
        
        # Get the first third-party vehicle for this client vehicle
        third_party_vehicle = db.query(ThirdPartyVehicle).filter(
            ThirdPartyVehicle.client_vehicle_id == client_vehicle.id
        ).first()
        
        if not third_party_vehicle:
            raise HTTPException(status_code=404, detail=f"No third-party vehicle found for claim {claim_id}")
        
        third_party_vehicle_id = third_party_vehicle.id
        
        tenant_id = get_tenant_id(request)
        svc = VehicleDamageReportEmailService(db, tenant_id)
        rpt = svc._compose_report_for_third_party(claim_id, third_party_vehicle_id)

        # Build normalized_report similar to /car-damage-detection/detect
        dd = rpt.detected_damages
        confidence_percent = dd.confidence_percent or 0
        if confidence_percent >= 80:
            confidence_bucket = "high"
        elif confidence_percent >= 60:
            confidence_bucket = "medium"
        else:
            confidence_bucket = "low"

        normalized_report = {
            "client_area_of_damage": rpt.vehicle_details and dd.area_of_damage or "",
            "client_unrelated_damage": rpt.client_unrelated_damage or "",
            "client_vehicle_status_id": None,
            "damage_diagram": {
                "ai_analysis": "comprehensive",
                "confidence": confidence_bucket,
                "detected_areas": [x.strip() for x in (dd.area_of_damage or "").split(",") if x.strip()],
                "detected_types": [x.strip() for x in (dd.type_of_damage or "").split(",") if x.strip()],
            },
            "damage_side": dd.damage_side or "",
            "area_of_damage": dd.area_of_damage or "",
            "type_of_damage": dd.type_of_damage or "",
            "severity": dd.severity or "",
            "confidence_percent": confidence_percent,
            "total_damaged_points_identified": dd.total_damaged_points_identified or 0,
            "suggested_repair_action": dd.ai_suggested_actions or "",
            "vehicle_status_id": None,
            "raw_result": {
                "summary": rpt.summary.dict() if hasattr(rpt.summary, "dict") else rpt.summary,
            },
        }

        images = [
            {"file_path": get_full_url(img.file_path), "original_filename": img.original_filename}
            for img in rpt.uploaded_images
        ] if rpt.uploaded_images else []

        response: Dict[str, Any] = {
            "predictions": {},
            "summary": {
                "total_detections": dd.total_damaged_points_identified or 0,
                "average_confidence": (confidence_percent or 0) / 100.0,
            },
            "metadata": {
                "report_id": rpt.report_details.report_id,
                "claim_id": rpt.report_details.claim_id,
                "third_party_vehicle_id": third_party_vehicle_id,
                "generated_on": rpt.report_details.generated_on,
            },
            "normalized_report": normalized_report,
            "images": images,
            # Vehicle details
            "vehicle_details": {
                "vehicle_reg_no": rpt.vehicle_details.vehicle_reg_no,
                "make_model": rpt.vehicle_details.make_model,
                "color": rpt.vehicle_details.color,
                "year": rpt.vehicle_details.year,
            } if rpt.vehicle_details else None,
            # Upload/Created by details
            "upload_details": {
                "uploaded_by": rpt.upload_details.uploaded_by,
                "file_name": rpt.upload_details.file_name,
                "uploaded_on": rpt.upload_details.uploaded_on,
                "source": rpt.upload_details.source,
            } if rpt.upload_details else None,
        }

        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating third-party vehicle damage report: {str(e)}")


@vehicle_router.post("/damage-report/{claim_id}/send-email", response_model=DamageReportEmailResponse)
def send_damage_report_email_router(
    claim_id: int,
    request: Request,
    email_data: DamageReportEmailRequest,
    db: Session = Depends(get_session)
):
    """
    Send comprehensive vehicle damage report via email
    Automatically fetches email from database and includes all vehicle data with AI analysis
    """
    try:
        tenant_id = get_tenant_id(request)
        email_service = VehicleDamageReportEmailService(db, tenant_id)

        # Determine recipient email from DB when not provided
        recipient_email = email_data.recipient_email
        if not recipient_email:
            from libdata.models.tables import Claim, Address, ClientDetail
            # Fetch client detail for claim
            client = (
                db.query(ClientDetail)
                .filter(ClientDetail.claim_id == claim_id, ClientDetail.role == 'CLIENT')
                .first()
            )
            if client and client.address and client.address.email:
                recipient_email = client.address.email
            else:
                # fallback: any address email related to claim
                addr = (
                    db.query(Address)
                    .join(Claim, Claim.id == claim_id)
                    .first()
                )
                if addr and addr.email:
                    recipient_email = addr.email

        if not recipient_email:
            raise HTTPException(status_code=400, detail="Recipient email not found for claim")

        # Send comprehensive damage report with all vehicle data
        result_message = email_service.send_comprehensive_damage_report_email(
            claim_id=claim_id,
            recipient_email=recipient_email,
            recipient_name=email_data.recipient_name or "Recipient",
            custom_message=email_data.message
        )
        
        return DamageReportEmailResponse(
            status="success",
            message=result_message,
            report_id=None
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending damage report email: {str(e)}")