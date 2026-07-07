"""
API endpoints for vehicle damage report versioning
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from libdata.settings import get_session
from appflow.utils import get_tenant_id
from appflow.services.vehicle_report_version_service import VehicleReportVersionService
from appflow.models.vehicle_report_version import (
    ReportVersionCreate,
    ReportVersionSummary,
    ReportVersionDetail,
    ReportVersionHistory,
    ReportVersionComparison,
    ReportVersionResponse
)
from libauth.auth import authenticate

logger = logging.getLogger(__name__)

version_router = APIRouter(prefix="/damage-reports/versions", tags=["Report Versions"])


@version_router.post("", response_model=ReportVersionResponse)
def create_report_version(
    version_data: ReportVersionCreate,
    request: Request,
    db: Session = Depends(get_session),
    user = Depends(authenticate)
):
    """
    Create a new version of a damage report.
    
    This should be called when:
    - New images are uploaded for an existing claim
    - Re-analysis is performed with updated AI
    - Manual corrections are made to damage assessment
    
    The system will:
    1. Find the latest version of the report
    2. Mark it as superseded
    3. Create a new version with incremented version number
    4. Add the new images to this version
    
    Example:
        POST /damage-reports/versions
        {
            "claim_id": 12345,
            "vehicle_id": 67,
            "vehicle_type": "client",
            "version_notes": "Added 3 more close-up photos of bumper damage",
            "damage_side": "Front",
            "area_of_damage": "Bumper, Hood",
            "severity": "Medium",
            "confidence_percent": 88,
            "images": [
                "uploads/claim_12345/new_image1.jpg",
                "uploads/claim_12345/new_image2.jpg",
                "uploads/claim_12345/new_image3.jpg"
            ]
        }
        
    Returns:
        ReportVersionResponse with new version number and details
    """
    try:
        tenant_id = get_tenant_id(request)
        user_id = user.get('user_id') if user else None
        
        service = VehicleReportVersionService(db, tenant_id, user_id)
        result = service.create_new_version(version_data)
        
        logger.info(
            f"User {user_id} created report version {result.new_version} "
            f"for claim {version_data.claim_id}"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating report version: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create report version"
        )


@version_router.get("/history/{claim_id}/{vehicle_type}", 
                   response_model=ReportVersionHistory)
def get_version_history(
    claim_id: int,
    vehicle_type: str,
    request: Request,
    db: Session = Depends(get_session),
    user = Depends(authenticate)
):
    """
    Get complete version history for a vehicle's damage reports.
    Automatically detects vehicle ID based on claim and vehicle type.
    
    Returns all versions in reverse chronological order (latest first).
    
    Example:
        GET /damage-reports/versions/history/12345/client
        GET /damage-reports/versions/history/12345/third-party
        
    Returns:
        {
            "claim_id": 12345,
            "vehicle_id": 67,
            "vehicle_type": "client",
            "total_versions": 3,
            "latest_version": 3,
            "versions": [...]
        }
    """
    try:
        tenant_id = get_tenant_id(request)
        service = VehicleReportVersionService(db, tenant_id)
        
        # Validate vehicle_type
        if vehicle_type not in ['client', 'third_party']:
            raise HTTPException(
                status_code=400,
                detail="vehicle_type must be 'client' or 'third_party'"
            )
        
        return service.get_version_history_by_claim(claim_id, vehicle_type)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving version history: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve version history"
        )


@version_router.get("/{claim_id}/{vehicle_type}/{version}", 
                   response_model=ReportVersionDetail)
def get_specific_version(
    claim_id: int,
    vehicle_type: str,
    version: int,
    request: Request,
    db: Session = Depends(get_session),
    user = Depends(authenticate)
):
    """
    Get a specific version of a damage report.
    Automatically detects vehicle ID based on claim and vehicle type.
    
    Example:
        GET /damage-reports/versions/12345/client/2
        GET /damage-reports/versions/12345/third-party/2
        
        Returns version 2 of the report
    """
    try:
        tenant_id = get_tenant_id(request)
        service = VehicleReportVersionService(db, tenant_id)
        
        if vehicle_type not in ['client', 'third_party']:
            raise HTTPException(
                status_code=400,
                detail="vehicle_type must be 'client' or 'third_party'"
            )
        
        return service.get_specific_version_by_claim(claim_id, vehicle_type, version)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving version: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve report version"
        )


@version_router.get("/latest/{claim_id}/{vehicle_type}", 
                   response_model=ReportVersionDetail)
def get_latest_version(
    claim_id: int,
    vehicle_type: str,
    request: Request,
    db: Session = Depends(get_session),
    user = Depends(authenticate)
):
    """
    Get the latest version of a damage report.
    Automatically detects vehicle ID based on claim and vehicle type.
    
    Example:
        GET /damage-reports/versions/latest/12345/client
        GET /damage-reports/versions/latest/12345/third-party
    """
    try:
        tenant_id = get_tenant_id(request)
        service = VehicleReportVersionService(db, tenant_id)
        
        if vehicle_type not in ['client', 'third_party']:
            raise HTTPException(
                status_code=400,
                detail="vehicle_type must be 'client' or 'third_party'"
            )
        
        return service.get_latest_version_by_claim(claim_id, vehicle_type)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving latest version: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve latest version"
        )


@version_router.get("/compare/{claim_id}/{vehicle_type}", 
                   response_model=ReportVersionComparison)
def compare_versions(
    claim_id: int,
    vehicle_type: str,
    request: Request,
    version_from: int = Query(..., description="Earlier version to compare"),
    version_to: int = Query(..., description="Later version to compare"),
    db: Session = Depends(get_session),
    user = Depends(authenticate)
):
    """
    Compare two versions of a damage report.
    Automatically detects vehicle ID based on claim and vehicle type.
    
    Example:
        GET /damage-reports/versions/compare/12345/client?version_from=1&version_to=3
        GET /damage-reports/versions/compare/12345/third-party?version_from=1&version_to=3
        
    Returns:
        {
            "claim_id": 12345,
            "vehicle_id": 67,
            "vehicle_type": "client",
            "version_from": { ...version 1 details... },
            "version_to": { ...version 3 details... },
            "changes": {
                "severity": {"from": "Low", "to": "Medium"}
            },
            "new_images_count": 3,
            "removed_images_count": 0
        }
    """
    try:
        tenant_id = get_tenant_id(request)
        service = VehicleReportVersionService(db, tenant_id)
        
        if vehicle_type not in ['client', 'third_party']:
            raise HTTPException(
                status_code=400,
                detail="vehicle_type must be 'client' or 'third_party'"
            )
        
        if version_from >= version_to:
            raise HTTPException(
                status_code=400,
                detail="version_from must be less than version_to"
            )
        
        return service.compare_versions_by_claim(
            claim_id, vehicle_type, version_from, version_to
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error comparing versions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to compare versions"
        )


@version_router.post("/rollback/{claim_id}/{vehicle_type}/{target_version}", 
                    response_model=ReportVersionResponse)
def rollback_to_version(
    claim_id: int,
    vehicle_type: str,
    target_version: int,
    request: Request,
    rollback_notes: Optional[str] = Query(None, description="Reason for rollback"),
    db: Session = Depends(get_session),
    user = Depends(authenticate)
):
    """
    Rollback to a previous version of the report.
    Automatically detects vehicle ID based on claim and vehicle type.
    
    Creates a NEW version that's a copy of the target version.
    Doesn't delete newer versions - they remain in history.
    
    Example:
        POST /damage-reports/versions/rollback/12345/client/2?rollback_notes=Version 3 had errors
        POST /damage-reports/versions/rollback/12345/third-party/2
        
    Returns:
        New version number (e.g., if latest was 3, creates version 4 as copy of version 2)
    """
    try:
        tenant_id = get_tenant_id(request)
        user_id = user.get('user_id') if user else None
        
        service = VehicleReportVersionService(db, tenant_id, user_id)
        
        if vehicle_type not in ['client', 'third_party']:
            raise HTTPException(
                status_code=400,
                detail="vehicle_type must be 'client' or 'third_party'"
            )
        
        result = service.rollback_to_version_by_claim(
            claim_id, vehicle_type, target_version, rollback_notes
        )
        
        logger.info(
            f"User {user_id} rolled back claim {claim_id} to version {target_version}. "
            f"Created new version {result.new_version}"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error rolling back version: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to rollback version"
        )

