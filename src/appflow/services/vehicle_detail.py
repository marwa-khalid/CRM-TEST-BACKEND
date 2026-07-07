from sqlalchemy.orm import Session
from fastapi import HTTPException, status, UploadFile
import os
from datetime import datetime

from libdata.models.tables import VehicleDetail, Borough, ThirdPartyVehicle, Claim, VehicleDamageAIReport, VehicleDamageAIImage, User, VehicleStatus, TaxiType
from appflow.models.vehicle_detail import (
    ClientVehicleCreate, ClientVehicleResponse,
    BoroughCreate,
    ThirdPartyVehicleCreate,
    VehicleDamageBatchUpdate,
    VehicleDamageAIReportIn
)
from appflow.utils import get_full_url,get_tenant_id,actor_id,build_case_reference
from appflow.services.cloudinary_service import cloudinary_service
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType

def normalize_claim_type(claim_type: str) -> str:
    # Normalize any non-standard dash characters to standard hyphen
    return claim_type.replace("–", "-")

def normalize_borough_payload(db: Session, borough_data: BoroughCreate) -> dict:
    data = borough_data.dict()
    taxi_type_id = data.get("taxi_type_id")

    if taxi_type_id and not db.query(TaxiType.id).filter(TaxiType.id == taxi_type_id).first():
        data["taxi_type_id"] = None

    return data

def create_client_vehicle(vehicle_data: ClientVehicleCreate, db: Session,request) -> VehicleDetail:
    tenant_id = get_tenant_id(request)
    current_user_id = actor_id(request)
    # Validate claim
    claim = db.query(Claim).filter(Claim.id == vehicle_data.claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    # Claim may not have a claim type yet — skip the type-specific checks if so.
    claim_type_label = (
        normalize_claim_type(claim.claim_type.label.strip())
        if claim.claim_type and claim.claim_type.label
        else None
    )

    # Check for RTA-NA or RTA CAMS claim types and ensure borough is provided
    if claim_type_label in ["RTA-NA"]:
        if not vehicle_data.borough:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Borough information is required"
            )

    # Create Client Vehicle
    vehicle = VehicleDetail(
        claim_id=vehicle_data.claim_id,
        make=vehicle_data.make,
        model=vehicle_data.model,
        body_type=vehicle_data.body_type,
        registration=vehicle_data.registration,
        color=vehicle_data.color,
        fuel_type_id=vehicle_data.fuel_type_id,
        engine_size=vehicle_data.engine_size,
        transmission_id=vehicle_data.transmission_id,
        number_of_seat=vehicle_data.number_of_seat,
        vehicle_category=vehicle_data.vehicle_category,
        # vehicle_status_id=vehicle_data.vehicle_status_id,
        # damage_area=vehicle_data.damage_area,
        # unrelated_damage=vehicle_data.unrelated_damage,
        tenant_id=claim.tenant_id,
        created_by=current_user_id,
        updated_by=current_user_id
    )
    db.add(vehicle)
    db.flush()  # to get vehicle.id

    # Borough
    if vehicle_data.borough:
        borough_data = normalize_borough_payload(db, vehicle_data.borough)
        borough = Borough(
            client_vehicle_id=vehicle.id,
            borough_name=borough_data.get("borough_name"),
            taxi_type_id=borough_data.get("taxi_type_id"),
            client_badge_number=borough_data.get("client_badge_number"),
            badge_expiration_date=borough_data.get("badge_expiration_date"),
            vehicle_badge_number=borough_data.get("vehicle_badge_number"),
            any_other_borough=borough_data.get("any_other_borough"),
            other_borough_name=borough_data.get("other_borough_name"),
            tenant_id=claim.tenant_id,
            created_by=current_user_id,
            updated_by=current_user_id
        )
        db.add(borough)

    # Third Party Vehicles
    for i, tp_data in enumerate(vehicle_data.third_party_vehicles, start=1):
        tp_vehicle = ThirdPartyVehicle(
            client_vehicle_id=vehicle.id,
            sequence=i,
            make=tp_data.make,
            model=tp_data.model,
            registration=tp_data.registration,
            color=tp_data.color,
            images_available=tp_data.images_available,
            created_by=current_user_id,
            updated_by=current_user_id
            # vehicle_status_id=tp_data.vehicle_status_id,
            # damage_area=tp_data.damage_area,
            # unrelated_damage=tp_data.unrelated_damage,
        )
        db.add(tp_vehicle)

    db.commit()
    db.refresh(vehicle)
    reference = build_case_reference(claim.id,db)
    HistoryActivityService.create_activity(
        db=db,
        claim_id=claim.id,
        file_name=f"The vehicle detail has been created for claim {reference}",
        file_path="",
        file_type=HistoryLogType.CREATED_VEHICLE_DETAIL,
        user_id=current_user_id,
        tenant_id=tenant_id
    )
    return vehicle

def update_client_vehicle(claim_id: int, vehicle_data: ClientVehicleCreate, db: Session,request) -> VehicleDetail:
    tenant_id = get_tenant_id(request)
    current_user_id = actor_id(request)
    # Get the existing vehicle based on claim_id
    vehicle = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client vehicle not found")

    # Get the claim to validate claim type
    claim = db.query(Claim).filter(Claim.id == vehicle.claim_id).first()
    # Claim may not have a claim type yet — skip the type-specific checks if so.
    claim_type_label = (
        normalize_claim_type(claim.claim_type.label.strip())
        if claim and claim.claim_type and claim.claim_type.label
        else None
    )

    changed_fields = []

    # ✅ RTA validation
    if claim_type_label in ["RTA-NA", "RTA CAMS"] and not vehicle_data.borough:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Borough information is Required"
        )

    # ✅ compare primitive fields
    for field, value in vehicle_data.dict(exclude={"borough", "third_party_vehicles", "claim_id", "tenant_id","damage_area",
        "unrelated_damage",}).items():
        old_value = getattr(vehicle, field)
        if old_value != value:
            changed_fields.append(field)
            setattr(vehicle, field, value)

    # ✅ borough change detection
    if vehicle_data.borough:
        borough_data = normalize_borough_payload(db, vehicle_data.borough)
        if vehicle.borough:
            vehicle.borough.updated_by = current_user_id
            for field, value in borough_data.items():
                old_value = getattr(vehicle.borough, field)
                if old_value != value:
                    changed_fields.append(f"borough.{field}")
                setattr(vehicle.borough, field, value)
        else:
            changed_fields.append("borough")
            borough = Borough(client_vehicle_id=vehicle.id, **borough_data)
            borough.created_by = current_user_id
            borough.updated_by = current_user_id
            db.add(borough)

    # ✅ third party detection
    existing_tp = db.query(ThirdPartyVehicle).filter(ThirdPartyVehicle.client_vehicle_id == vehicle.id,ThirdPartyVehicle.is_active == True).all()

    # Convert to dictionary for easy lookup
    existing_tp_dict = {tp.sequence: tp for tp in existing_tp}

    # Track changes for third party vehicles
    tp_changed_fields = set()

    # ✅ Process each new third party vehicle
    for i, tp_data in enumerate(vehicle_data.third_party_vehicles, start=1):
        sequence = i

        if sequence in existing_tp_dict:
            # UPDATE existing third party vehicle if data doesn't match
            tp_vehicle = existing_tp_dict[sequence]
            tp_vehicle.updated_by = current_user_id

            # Check individual field changes
            if tp_vehicle.make != tp_data.make:
                tp_changed_fields.add(f"third_party.make.sequence_{sequence}")
                tp_vehicle.make = tp_data.make

            if tp_vehicle.model != tp_data.model:
                tp_changed_fields.add(f"third_party.model.sequence_{sequence}")
                tp_vehicle.model = tp_data.model

            if tp_vehicle.registration != tp_data.registration:
                tp_changed_fields.add(f"third_party.registration.sequence_{sequence}")
                tp_vehicle.registration = tp_data.registration

            if tp_vehicle.color != tp_data.color:
                tp_changed_fields.add(f"third_party.color.sequence_{sequence}")
                tp_vehicle.color = tp_data.color

            if tp_vehicle.images_available != tp_data.images_available:
                tp_changed_fields.add(f"third_party.images_available.sequence_{sequence}")
                tp_vehicle.images_available = tp_data.images_available

            # Reactivate if it was soft deleted
            if not tp_vehicle.is_active:
                tp_changed_fields.add(f"third_party.reactivated.sequence_{sequence}")
                tp_vehicle.is_active = True

        else:
            # CREATE new third party vehicle if sequence doesn't exist
            tp_changed_fields.add(f"third_party.added.sequence_{sequence}")

            tp_vehicle = ThirdPartyVehicle(
                client_vehicle_id=vehicle.id,
                sequence=sequence,
                make=tp_data.make,
                model=tp_data.model,
                registration=tp_data.registration,
                color=tp_data.color,
                images_available=tp_data.images_available,
                is_active=True,
                created_by=current_user_id,
                updated_by=current_user_id
            )
            db.add(tp_vehicle)

    # ✅ Soft delete any extra third party vehicles that are no longer in the request
    requested_sequences = set(range(1, len(vehicle_data.third_party_vehicles) + 1))
    existing_sequences = set(existing_tp_dict.keys())

    sequences_to_soft_delete = existing_sequences - requested_sequences
    if sequences_to_soft_delete:
        for seq in sequences_to_soft_delete:
            if existing_tp_dict[seq].is_active:  # Only track if it was active
                tp_changed_fields.add(f"third_party.deleted.sequence_{seq}")
                existing_tp_dict[seq].is_active = False
                existing_tp_dict[seq].updated_by = current_user_id

    # ✅ Add third party changes to changed_fields
    if tp_changed_fields:
        changed_fields.extend(tp_changed_fields)

    vehicle.updated_by = current_user_id
    db.commit()
    db.refresh(vehicle)
    # ✅ field label map
    field_label_map = {
        "make": "Vehicle Make",
        "model": "Vehicle Model",
        "body_type": "Body Type",
        "registration": "Registration Number",
        "color": "Vehicle Color",
        "fuel_type_id": "Fuel Type",
        "engine_size": "Engine Size",
        "transmission_id": "Transmission Type",
        "number_of_seat": "Number of Seats",
        "vehicle_category": "Vehicle Category",
        "third_party_vehicles": "Third Party Vehicles",
    }
    borough_field_label_map = {
        "borough_name": "Borough Name",
        "client_badge_number": "Client Badge Number",
        "badge_expiration_date": "Badge Expiration Date",
        "vehicle_badge_number": "Vehicle Badge Number",
        "any_other_borough": "Any Other Borough",
        "other_borough_name": "Other Borough Name",
        "taxi_type_id": "Taxi Type",
    }

    # ✅ third party field label map
    third_party_field_label_map = {
        "third_party.make": "Third Party Vehicle Make",
        "third_party.model": "Third Party Vehicle Model",
        "third_party.registration": "Third Party Registration",
        "third_party.color": "Third Party Vehicle Color",
        "third_party.images_available": "Third Party Images Available",
        "third_party.added": "Third Party Vehicle Added",
        "third_party.deleted": "Third Party Vehicle Removed",
        "third_party.reactivated": "Third Party Vehicle Reactivated",
    }

    # ✅ convert to readable format
    readable_changes = []
    for field in changed_fields:
        if field in field_label_map:
            readable_changes.append(field_label_map[field])
        elif field.startswith("borough."):
            key = field.split(".")[1]
            readable_changes.append(borough_field_label_map.get(key, key))
        elif field.startswith("third_party."):
            # Handle third party fields with sequence numbers
            if "sequence_" in field:
                base_field = field.split(".sequence_")[0]
                sequence_num = field.split(".sequence_")[1]
                label = third_party_field_label_map.get(base_field, base_field)
                readable_changes.append(f"{label} (Vehicle {sequence_num})")
            else:
                readable_changes.append(third_party_field_label_map.get(field, field))
        else:
            readable_changes.append(field)

    # ✅ create activity log
    if readable_changes:
        file_path = ", ".join(readable_changes)
        reference = build_case_reference(claim.id, db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=claim.id,
            file_name=f"The vehicle detail has been updated for claim {reference}",
            file_path=file_path,
            file_type=HistoryLogType.UPDATED_VEHICLE_DETAIL,
            user_id=current_user_id,
            tenant_id=tenant_id
        )
    return vehicle

def get_client_vehicle(claim_id: int, db: Session) -> VehicleDetail:
    from sqlalchemy.orm import joinedload
    
    vehicle = db.query(VehicleDetail)\
        .options(
            joinedload(VehicleDetail.ai_reports).joinedload(VehicleDamageAIReport.images),
            joinedload(VehicleDetail.third_party_vehicles).joinedload(ThirdPartyVehicle.ai_reports).joinedload(VehicleDamageAIReport.images)
        )\
        .filter(VehicleDetail.claim_id == claim_id)\
        .first()
    
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client vehicle not found")
    return vehicle


def list_client_vehicles(claim_id: int, db: Session):
    from sqlalchemy.orm import joinedload
    
    return db.query(VehicleDetail)\
        .options(
            joinedload(VehicleDetail.ai_reports).joinedload(VehicleDamageAIReport.images),
            joinedload(VehicleDetail.third_party_vehicles).joinedload(ThirdPartyVehicle.ai_reports).joinedload(VehicleDamageAIReport.images)
        )\
        .filter(VehicleDetail.claim_id == claim_id)\
        .all()


def deactivate_client_vehicle(vehicle_id: int, db: Session):
    vehicle = get_client_vehicle(vehicle_id, db)
    vehicle.is_active=False
    db.commit()
    return {"message": "Client vehicle Deactivated successfully"}


def update_vehicle_damage(payload: VehicleDamageBatchUpdate, db: Session):
    from libdata.models.tables import VehicleStatus
    
    # Update client vehicle damage if provided
    if payload.vehicle_detail:
        v = db.query(VehicleDetail).filter(VehicleDetail.id == payload.vehicle_detail.id).first()
        if v:
            if payload.vehicle_detail.client_area_of_damage is not None:
                v.damage_area = payload.vehicle_detail.client_area_of_damage
            if payload.vehicle_detail.client_unrelated_damage is not None:
                v.unrelated_damage = payload.vehicle_detail.client_unrelated_damage
            if payload.vehicle_detail.client_vehicle_status_id is not None:
                # Validate vehicle_status_id exists, set to None if invalid
                if payload.vehicle_detail.client_vehicle_status_id > 0:
                    status_exists = db.query(VehicleStatus).filter(VehicleStatus.id == payload.vehicle_detail.client_vehicle_status_id).first()
                    v.vehicle_status_id = payload.vehicle_detail.client_vehicle_status_id if status_exists else None
                else:
                    v.vehicle_status_id = None
            if payload.vehicle_detail.damage_diagram is not None:
                v.damage_diagram = payload.vehicle_detail.damage_diagram

    # Update third-party vehicle damage if provided
    if payload.third_party_vehicle_detail:
        tp = db.query(ThirdPartyVehicle).filter(ThirdPartyVehicle.id == payload.third_party_vehicle_detail.id).first()
        if tp:
            if payload.third_party_vehicle_detail.client_area_of_damage is not None:
                tp.damage_area = payload.third_party_vehicle_detail.client_area_of_damage
            if payload.third_party_vehicle_detail.client_unrelated_damage is not None:
                tp.unrelated_damage = payload.third_party_vehicle_detail.client_unrelated_damage
            if payload.third_party_vehicle_detail.client_vehicle_status_id is not None:
                # Validate vehicle_status_id exists, set to None if invalid
                if payload.third_party_vehicle_detail.client_vehicle_status_id > 0:
                    status_exists = db.query(VehicleStatus).filter(VehicleStatus.id == payload.third_party_vehicle_detail.client_vehicle_status_id).first()
                    tp.vehicle_status_id = payload.third_party_vehicle_detail.client_vehicle_status_id if status_exists else None
                else:
                    tp.vehicle_status_id = None
            if payload.third_party_vehicle_detail.damage_diagram is not None:
                tp.damage_diagram = payload.third_party_vehicle_detail.damage_diagram

    db.commit()
    # db.refresh()
    return {"message": "Vehicle damages updated"}


def create_ai_damage_report(data: VehicleDamageAIReportIn, image_paths: list[str], db: Session, tenant_id: int = None, user_id: int = None) -> list[VehicleDamageAIReport]:
    """
    Create AI damage reports with automatic versioning support.
    
    - First upload: Creates Version 1
    - Subsequent uploads: Creates Version 2, 3, etc. and supersedes previous versions
    - Works for both client and third-party vehicles
    """
    from appflow.services.vehicle_report_version_service import VehicleReportVersionService
    from appflow.models.vehicle_report_version import ReportVersionCreate
    
    reports = []
    status_cache: dict[int, int] = {}
    status_label_cache: dict[str, int] = {}

    def resolve_vehicle_status_id(status_id: int | None) -> int | None:
        if status_id is None:
            return None
        if status_id <= 0:
            return None
        if status_id in status_cache:
            return status_cache[status_id]

        exists = (
            db.query(VehicleStatus.id)
            .filter(VehicleStatus.id == status_id)
            .scalar()
        )
        if exists is None:
            return None

        status_cache[status_id] = status_id
        return status_id

    def determine_vehicle_status_label(severity: str | None) -> str:
        if not severity:
            return "TBC"
        key = severity.strip().lower()
        if any(term in key for term in ("high", "severe", "critical")):
            return "Unroadworthy"
        if any(term in key for term in ("medium", "moderate")):
            return "TBC"
        if any(term in key for term in ("low", "minor")):
            return "Roadworthy"
        return "TBC"

    def determine_vehicle_status_id(severity: str | None) -> int:
        label = determine_vehicle_status_label(severity)
        cache_key = label.lower()
        if cache_key in status_label_cache:
            return status_label_cache[cache_key]

        status_id = (
            db.query(VehicleStatus.id)
            .filter(VehicleStatus.label == label)
            .scalar()
        )
        if status_id is None:
            status_id = (
                db.query(VehicleStatus.id)
                .order_by(VehicleStatus.sort_order)
                .scalar()
            )
        if status_id is None:
            raise ValueError("No vehicle statuses are configured in the system.")

        status_label_cache[cache_key] = status_id
        return status_id
    
    # Validate that at least one vehicle is provided
    if not data.vehicle_detail and not data.third_party_vehicle_detail:
        raise ValueError("At least one vehicle (client or third-party) must be provided for AI damage report creation")
    
    # Helper function to merge global AI fields with vehicle-specific fields
    def merge_ai_fields(vehicle_data) -> dict:
        severity_value = getattr(vehicle_data, 'severity', None) or data.severity
        raw_status_id = getattr(vehicle_data, 'vehicle_status_id', None) or data.vehicle_status_id
        resolved_status_id = resolve_vehicle_status_id(raw_status_id)
        if resolved_status_id is None:
            resolved_status_id = determine_vehicle_status_id(severity_value)

        return {
            "damage_side": getattr(vehicle_data, 'damage_side', None) or data.damage_side,
            "area_of_damage": getattr(vehicle_data, 'area_of_damage', None) or data.area_of_damage,
            "type_of_damage": getattr(vehicle_data, 'type_of_damage', None) or data.type_of_damage,
            "severity": getattr(vehicle_data, 'severity', None) or data.severity,
            "confidence_percent": getattr(vehicle_data, 'confidence_percent', None) or data.confidence_percent,
            "total_damaged_points_identified": getattr(vehicle_data, 'total_damaged_points_identified', None) or data.total_damaged_points_identified,
            "suggested_repair_action": getattr(vehicle_data, 'suggested_repair_action', None) or data.suggested_repair_action,
            "vehicle_status_id": resolved_status_id,
            "raw_result": getattr(vehicle_data, 'raw_result', None) or data.raw_result
        }
    
    # Create report for client vehicle if provided (WITH VERSIONING)
    if data.vehicle_detail:
        # Validate client vehicle ID exists
        if not data.vehicle_detail.id or data.vehicle_detail.id <= 0:
            raise ValueError(f"Invalid client vehicle ID: {data.vehicle_detail.id}. Must be a positive integer.")
        
        # Verify the client vehicle exists in the database
        client_vehicle = db.query(VehicleDetail).filter(
            VehicleDetail.id == data.vehicle_detail.id,
            VehicleDetail.claim_id == data.claim_id
        ).first()
        
        if not client_vehicle:
            raise ValueError(f"Client vehicle with ID {data.vehicle_detail.id} not found for claim {data.claim_id}")
        
        # Check if a report already exists (for versioning)
        existing_report = db.query(VehicleDamageAIReport).filter(
            VehicleDamageAIReport.claim_id == data.claim_id,
            VehicleDamageAIReport.client_vehicle_id == data.vehicle_detail.id,
            VehicleDamageAIReport.is_latest == True
        ).first()
        
        ai_fields = merge_ai_fields(data.vehicle_detail)
        
        if existing_report:
            # Version exists - create new version via versioning service
            version_service = VehicleReportVersionService(db, tenant_id or client_vehicle.tenant_id, user_id)
            
            version_data = ReportVersionCreate(
                claim_id=data.claim_id,
                vehicle_id=data.vehicle_detail.id,
                vehicle_type='client',
                version_notes=f"Updated with {len(data.vehicle_detail.images or image_paths)} new images",
                images=data.vehicle_detail.images or image_paths,
                **ai_fields
            )
            
            version_response = version_service.create_new_version(version_data)
            
            # Get the newly created report
            report = db.query(VehicleDamageAIReport).get(version_response.report_id)
            reports.append(report)
            
        else:
            # First version - create directly with version = 1
            report = VehicleDamageAIReport(
                claim_id=data.claim_id,
                client_vehicle_id=data.vehicle_detail.id,
                third_party_vehicle_id=None,
                version=1,
                is_latest=True,
                version_notes="Initial report",
                **ai_fields
            )
            db.add(report)
            db.flush()  # Get the ID
            reference = build_case_reference(data.claim_id,db)
            # Get image paths for file_path (convert list to comma-separated string)
            image_paths_for_history = data.vehicle_detail.images if data.vehicle_detail and data.vehicle_detail.images else (data.images or image_paths or [])
            file_path_str = ", ".join(image_paths_for_history) if image_paths_for_history else ""
            if not user_id:
                raise ValueError("user_id is required for AI report history activity")

            if not tenant_id:
                raise ValueError("tenant_id is required for AI report history activity")
            HistoryActivityService.create_activity(
                db=db,
                claim_id=data.claim_id,
                file_name=f"The ai report for claim {reference}",
                file_path=file_path_str,
                file_type=HistoryLogType.AI_REPORT,
                tenant_id=tenant_id,
                user_id=user_id
            )
            reports.append(report)
        
        # Update vehicle damage fields
        v = db.query(VehicleDetail).filter(VehicleDetail.id == data.vehicle_detail.id).first()
        if v:
            if data.vehicle_detail.client_area_of_damage is not None:
                v.damage_area = data.vehicle_detail.client_area_of_damage
            if data.vehicle_detail.client_unrelated_damage is not None:
                v.unrelated_damage = data.vehicle_detail.client_unrelated_damage
            resolved_status = resolve_vehicle_status_id(data.vehicle_detail.client_vehicle_status_id)
            v.vehicle_status_id = resolved_status if resolved_status is not None else ai_fields["vehicle_status_id"]
            if data.vehicle_detail.damage_diagram is not None:
                v.damage_diagram = data.vehicle_detail.damage_diagram
    
    # Create report for third-party vehicle if provided (WITH VERSIONING)
    if data.third_party_vehicle_detail:
        # Validate third-party vehicle ID exists
        if not data.third_party_vehicle_detail.id or data.third_party_vehicle_detail.id <= 0:
            raise ValueError(f"Invalid third-party vehicle ID: {data.third_party_vehicle_detail.id}. Must be a positive integer.")
        
        # Verify the third-party vehicle exists in the database
        third_party_vehicle = db.query(ThirdPartyVehicle).filter(
            ThirdPartyVehicle.id == data.third_party_vehicle_detail.id
        ).first()
        
        if not third_party_vehicle:
            raise ValueError(f"Third-party vehicle with ID {data.third_party_vehicle_detail.id} not found")
        
        # Check if a report already exists (for versioning)
        existing_report = db.query(VehicleDamageAIReport).filter(
            VehicleDamageAIReport.claim_id == data.claim_id,
            VehicleDamageAIReport.third_party_vehicle_id == data.third_party_vehicle_detail.id,
            VehicleDamageAIReport.is_latest == True
        ).first()
        
        ai_fields = merge_ai_fields(data.third_party_vehicle_detail)
        
        # Get client vehicle for tenant_id
        client_vehicle = db.query(VehicleDetail).filter(VehicleDetail.claim_id == data.claim_id).first()
        
        if existing_report:
            # Version exists - create new version via versioning service
            version_service = VehicleReportVersionService(db, tenant_id or (client_vehicle.tenant_id if client_vehicle else None), user_id)
            
            version_data = ReportVersionCreate(
                claim_id=data.claim_id,
                vehicle_id=data.third_party_vehicle_detail.id,
                vehicle_type='third_party',
                version_notes=f"Updated with {len(data.third_party_vehicle_detail.images or image_paths)} new images",
                images=data.third_party_vehicle_detail.images or image_paths,
                **ai_fields
            )
            
            version_response = version_service.create_new_version(version_data)
            
            # Get the newly created report
            report = db.query(VehicleDamageAIReport).get(version_response.report_id)
            reports.append(report)
            
        else:
            # First version - create directly with version = 1
            report = VehicleDamageAIReport(
                claim_id=data.claim_id,
                client_vehicle_id=None,
                third_party_vehicle_id=data.third_party_vehicle_detail.id,
                version=1,
                is_latest=True,
                version_notes="Initial report",
                **ai_fields
            )
            db.add(report)
            db.flush()  # Get the ID
            reports.append(report)
        
        # Update third-party vehicle damage fields
        tp = db.query(ThirdPartyVehicle).filter(ThirdPartyVehicle.id == data.third_party_vehicle_detail.id).first()
        if tp:
            if data.third_party_vehicle_detail.client_area_of_damage is not None:
                tp.damage_area = data.third_party_vehicle_detail.client_area_of_damage
            if data.third_party_vehicle_detail.client_unrelated_damage is not None:
                tp.unrelated_damage = data.third_party_vehicle_detail.client_unrelated_damage
            resolved_status = resolve_vehicle_status_id(data.third_party_vehicle_detail.client_vehicle_status_id)
            tp.vehicle_status_id = resolved_status if resolved_status is not None else ai_fields["vehicle_status_id"]
            if data.third_party_vehicle_detail.damage_diagram is not None:
                tp.damage_diagram = data.third_party_vehicle_detail.damage_diagram

    # Create image records for FIRST versions only (subsequent versions handled by versioning service)
    for report in reports:
        # Only add images if this is version 1 (first version)
        # Subsequent versions are handled by the versioning service
        if report.version == 1:
            # Determine which vehicle this report belongs to
            if report.client_vehicle_id and data.vehicle_detail and data.vehicle_detail.images:
                # This is a client vehicle report, use client vehicle images
                for path in data.vehicle_detail.images:
                    db.add(VehicleDamageAIImage(report_id=report.id, file_path=path, original_filename=path.split('/')[-1], created_by=user_id))
            elif report.third_party_vehicle_id and data.third_party_vehicle_detail and data.third_party_vehicle_detail.images:
                # This is a third-party vehicle report, use third-party vehicle images
                for path in data.third_party_vehicle_detail.images:
                    db.add(VehicleDamageAIImage(report_id=report.id, file_path=path, original_filename=path.split('/')[-1], created_by=user_id))
            elif image_paths:
                # Fallback to global image_paths if no per-vehicle images specified
                for path in image_paths:
                    db.add(VehicleDamageAIImage(report_id=report.id, file_path=path, original_filename=path.split('/')[-1], created_by=user_id))

    db.commit()
    
    # Refresh reports to load relationships (vehicle details, images, audit fields)
    for report in reports:
        db.refresh(report)
    
    return reports


def save_ai_images(claim_id: int, vehicle_detail_id: int | None, third_party_vehicle_id: int | None, files: list[UploadFile] | None) -> list[str]:
    """
    Upload images to Cloudinary and return their URLs
    """
    if not files:
        return []
    
    try:
        # Upload images to Cloudinary
        uploaded_images = cloudinary_service.upload_multiple_images(
            files=files,
            folder="vehicle-damage",
            claim_id=claim_id
        )
        
        # Return list of Cloudinary URLs
        return [img["file_path"] for img in uploaded_images]
    except Exception as e:
        print(f"Error uploading images to Cloudinary: {str(e)}")
        # Fall back to empty list if upload fails
        return []


def get_comprehensive_vehicle_damage_report(claim_id: int, db: Session) -> dict:
    """
    Get comprehensive vehicle damage report for a claim
    Returns all damage data in the format matching the UI
    """
    from datetime import datetime
    from sqlalchemy.orm import joinedload
    
    # Get claim details
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise ValueError(f"Claim {claim_id} not found")
    
    # Get client vehicle with all related data
    client_vehicle = db.query(VehicleDetail).options(
        joinedload(VehicleDetail.vehicle_status),
        joinedload(VehicleDetail.ai_reports).joinedload(VehicleDamageAIReport.images),
        joinedload(VehicleDetail.third_party_vehicles).joinedload(ThirdPartyVehicle.ai_reports).joinedload(VehicleDamageAIReport.images)
    ).filter(VehicleDetail.claim_id == claim_id).first()
    
    if not client_vehicle:
        raise ValueError(f"No client vehicle found for claim {claim_id}")
    
    # Get the latest AI report for client vehicle
    latest_ai_report = None
    if client_vehicle.ai_reports:
        latest_ai_report = max(client_vehicle.ai_reports, key=lambda x: x.created_at)
    
    # Get user who created the latest report (for upload details)
    uploaded_by = "System"
    if latest_ai_report and latest_ai_report.created_by:
        user = db.query(User).filter(User.id == latest_ai_report.created_by).first()
        if user:
            uploaded_by = f"{user.first_name} {user.last_name}".strip() or user.email
    
    # Format report details
    report_details = {
        "claim_id": f"A{claim_id:09d}",
        "report_id": f"A{claim_id:011d}",
        "generated_on": latest_ai_report.created_at.strftime("%d/%m/%Y, %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y, %I:%M %p")
    }
    
    # Format upload details
    upload_details = {
        "uploaded_by": uploaded_by,
        "file_name": "Damage Report",
        "uploaded_on": latest_ai_report.created_at.strftime("%d/%m/%Y, %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
        "source": "Camera"
    }
    
    # Format vehicle details
    vehicle_details = {
        "vehicle_reg_no": client_vehicle.registration,
        "make_model": f"{client_vehicle.make} {client_vehicle.model}",
        "color": client_vehicle.color or "Unknown",
        "year": "2022"  # This would need to be added to the vehicle model
    }
    
    # Format detected damages from AI report
    if latest_ai_report:
        detected_damages = {
            "damage_side": latest_ai_report.damage_side or "",
            "area_of_damage": latest_ai_report.area_of_damage or "",
            "type_of_damage": latest_ai_report.type_of_damage or "",
            "severity": latest_ai_report.severity or "",
            "confidence_percent": latest_ai_report.confidence_percent or 0,
            "total_damaged_points_identified": latest_ai_report.total_damaged_points_identified or 0,
            "ai_suggested_actions": latest_ai_report.suggested_repair_action or ""
        }
    else:
        # No AI report available, use manual damage data or defaults
        detected_damages = {
            "damage_side": "",
            "area_of_damage": client_vehicle.damage_area or "",
            "type_of_damage": "",
            "severity": "",
            "confidence_percent": 0,
            "total_damaged_points_identified": 0,
            "ai_suggested_actions": "Manual assessment required"
        }
    
    # Format uploaded images
    uploaded_images = []
    if latest_ai_report and latest_ai_report.images:
        for img in latest_ai_report.images:
            uploaded_images.append({
                "file_path": get_full_url(img.file_path),
                "original_filename": img.original_filename or "damage_image.jpg",
                "thumbnail_url": get_full_url(img.file_path)  # In a real app, you'd generate thumbnails
            })
    
    # Format confirmation
    confirmation = {
        "confirmed_by": uploaded_by,
        "confirmed_at": latest_ai_report.created_at.strftime("%d/%m/%Y on %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y on %I:%M %p")
    }
    
    # Format summary
    if latest_ai_report:
        summary = {
            "total_by_severity": latest_ai_report.total_damaged_points_identified or 0,
            "area": latest_ai_report.area_of_damage or "",
            "estimated_work_category": latest_ai_report.suggested_repair_action or "Structural check advised"
        }
    else:
        summary = {
            "total_by_severity": 0,
            "area": client_vehicle.damage_area or "",
            "estimated_work_category": "Manual assessment required"
        }
    
    return {
        "report_details": report_details,
        "upload_details": upload_details,
        "vehicle_details": vehicle_details,
        "client_unrelated_damage": client_vehicle.unrelated_damage or "",
        "client_vehicle_status": client_vehicle.vehicle_status.label if client_vehicle.vehicle_status else "",
        "detected_damages": detected_damages,
        "uploaded_images": uploaded_images,
        "confirmation": confirmation,
        "summary": summary
    }
