"""
Service layer for vehicle damage report versioning
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, and_, func
from fastapi import HTTPException
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

from libdata.models.tables import (
    VehicleDamageAIReport,
    VehicleDamageAIImage,
    VehicleDetail,
    ThirdPartyVehicle,
    VehicleStatus
)
from appflow.models.vehicle_report_version import (
    ReportVersionCreate,
    ReportVersionSummary,
    ReportVersionDetail,
    ReportVersionHistory,
    ReportVersionComparison,
    ReportVersionResponse
)

logger = logging.getLogger(__name__)


class VehicleReportVersionService:
    """Service for managing vehicle damage report versions"""
    
    def __init__(self, db: Session, tenant_id: int, user_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._status_label_cache: Dict[str, int] = {}
    
    def create_new_version(
        self,
        version_data: ReportVersionCreate
    ) -> ReportVersionResponse:
        """
        Create a new version of a damage report.
        
        This is triggered when:
        - New images are uploaded for existing claim
        - Re-analysis is performed
        - Manual corrections are made
        
        Process:
        1. Find latest version of the report
        2. Mark it as superseded
        3. Create new version with incremented version number
        4. Link to parent version
        5. Add new images
        
        Args:
            version_data: Data for creating new version
            
        Returns:
            ReportVersionResponse with details of created version
        """
        try:
            # Get the latest version
            latest_report = self._get_latest_report(
                claim_id=version_data.claim_id,
                vehicle_id=version_data.vehicle_id,
                vehicle_type=version_data.vehicle_type
            )
            
            if latest_report:
                # There's an existing version - create new one
                new_version_number = latest_report.version + 1
                parent_id = latest_report.id
                
                # Mark old version as superseded
                self._supersede_report(latest_report)
                
                previous_version = latest_report.version
            else:
                # First version
                new_version_number = 1
                parent_id = None
                previous_version = None
            
            # Create new report version
            new_report = self._create_report_version(
                version_data=version_data,
                version_number=new_version_number,
                parent_id=parent_id,
                previous_status_id=latest_report.vehicle_status_id if latest_report else None
            )
            
            # Add images to new version
            if version_data.images:
                self._add_images_to_report(new_report.id, version_data.images)
            
            self.db.commit()
            
            logger.info(
                f"Created report version {new_version_number} for "
                f"{version_data.vehicle_type} vehicle {version_data.vehicle_id}, "
                f"claim {version_data.claim_id}"
            )
            
            return ReportVersionResponse(
                success=True,
                message=f"Successfully created version {new_version_number}",
                new_version=new_version_number,
                report_id=new_report.id,
                previous_version=previous_version,
                changes_summary=version_data.version_notes
            )
            
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.exception(f"Error creating report version: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create report version: {str(e)}"
            )
    
    def get_version_history(
        self,
        claim_id: int,
        vehicle_id: int,
        vehicle_type: str
    ) -> ReportVersionHistory:
        """
        Get complete version history for a vehicle's damage reports.
        
        Args:
            claim_id: Claim ID
            vehicle_id: Vehicle ID (client or third-party)
            vehicle_type: 'client' or 'third_party'
            
        Returns:
            ReportVersionHistory with all versions
        """
        # Build query based on vehicle type
        if vehicle_type == 'client':
            filter_conditions = and_(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.client_vehicle_id == vehicle_id
            )
        else:
            filter_conditions = and_(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.third_party_vehicle_id == vehicle_id
            )
        
        # Get all versions
        versions = (
            self.db.query(VehicleDamageAIReport)
            .options(joinedload(VehicleDamageAIReport.images))
            .filter(filter_conditions)
            .order_by(desc(VehicleDamageAIReport.version))
            .all()
        )
        
        if not versions:
            raise HTTPException(
                status_code=404,
                detail=f"No reports found for {vehicle_type} vehicle {vehicle_id}"
            )
        
        # Build version summaries
        version_summaries = []
        for v in versions:
            version_summaries.append(ReportVersionSummary(
                id=v.id,
                version=v.version,
                created_at=v.created_at,
                created_by=v.created_by,
                is_latest=v.is_latest,
                version_notes=v.version_notes,
                image_count=len(v.images) if v.images else 0,
                superseded_at=v.superseded_at,
                confidence_percent=v.confidence_percent,
                severity=v.severity,
                total_damaged_points=v.total_damaged_points_identified
            ))
        
        latest_version = max(v.version for v in versions)
        
        return ReportVersionHistory(
            claim_id=claim_id,
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_type,
            total_versions=len(versions),
            latest_version=latest_version,
            versions=version_summaries
        )
    
    def get_specific_version(
        self,
        claim_id: int,
        vehicle_id: int,
        vehicle_type: str,
        version: int
    ) -> ReportVersionDetail:
        """
        Get a specific version of a report.
        
        Args:
            claim_id: Claim ID
            vehicle_id: Vehicle ID
            vehicle_type: 'client' or 'third_party'
            version: Version number to retrieve
            
        Returns:
            ReportVersionDetail for the specified version
        """
        # Build query
        if vehicle_type == 'client':
            filter_conditions = and_(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.client_vehicle_id == vehicle_id,
                VehicleDamageAIReport.version == version
            )
        else:
            filter_conditions = and_(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.third_party_vehicle_id == vehicle_id,
                VehicleDamageAIReport.version == version
            )
        
        report = (
            self.db.query(VehicleDamageAIReport)
            .options(joinedload(VehicleDamageAIReport.images))
            .filter(filter_conditions)
            .first()
        )
        
        if not report:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for {vehicle_type} vehicle {vehicle_id}"
            )
        
        # Create the base response
        version_detail = ReportVersionDetail.from_orm(report)
        
        # Add upload details and vehicle details for third-party reports
        if vehicle_type == 'third_party':
            # Build upload details from DB (user + first image filename)
            uploaded_by_str = report.created_by
            try:
                from libdata.models.tables import User
                if report.created_by:
                    user = self.db.query(User).filter(User.id == report.created_by).first()
                    if user:
                        uploaded_by_str = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email or report.created_by
            except Exception:
                pass

            first_image_name = None
            if report.images and len(report.images) > 0:
                first = report.images[0]
                first_image_name = first.original_filename or (first.file_path.split('/')[-1] if first.file_path else None)

            upload_details = {
                "uploaded_by": uploaded_by_str,
                "file_name": first_image_name,
                "uploaded_on": report.created_at,
                "source": "AI Analysis" if report.raw_result else "User Upload"
            }
            version_detail.upload_details = upload_details
            
            # Get vehicle details from ThirdPartyVehicle
            from libdata.models.tables import ThirdPartyVehicle
            third_party_vehicle = self.db.query(ThirdPartyVehicle).filter(
                ThirdPartyVehicle.id == vehicle_id
            ).first()
            
            if third_party_vehicle:
                vehicle_details = {
                    "vehicle_reg_no": third_party_vehicle.registration,
                    "make_model": f"{third_party_vehicle.make} {third_party_vehicle.model}".strip(),
                    "color": third_party_vehicle.color,
                    "year": None  # ThirdPartyVehicle doesn't have year field
                }
                version_detail.vehicle_details = vehicle_details
        
        # Add upload details and vehicle details for client reports
        if vehicle_type == 'client':
            uploaded_by_str = report.created_by
            try:
                from libdata.models.tables import User
                if report.created_by:
                    user = self.db.query(User).filter(User.id == report.created_by).first()
                    if user:
                        uploaded_by_str = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email or report.created_by
            except Exception:
                pass

            first_image_name = None
            if report.images and len(report.images) > 0:
                first = report.images[0]
                first_image_name = first.original_filename or (first.file_path.split('/')[-1] if first.file_path else None)

            upload_details = {
                "uploaded_by": uploaded_by_str,
                "file_name": first_image_name,
                "uploaded_on": report.created_at,
                "source": "AI Analysis" if report.raw_result else "User Upload"
            }
            version_detail.upload_details = upload_details

            # Get vehicle details from client VehicleDetail
            from libdata.models.tables import VehicleDetail
            client_vehicle = self.db.query(VehicleDetail).filter(
                VehicleDetail.id == vehicle_id
            ).first()

            if client_vehicle:
                vehicle_details = {
                    "vehicle_reg_no": client_vehicle.registration,
                    "make_model": f"{client_vehicle.make} {client_vehicle.model}".strip(),
                    "color": client_vehicle.color,
                    "year": None
                }
                version_detail.vehicle_details = vehicle_details
        
        return version_detail
    
    def compare_versions(
        self,
        claim_id: int,
        vehicle_id: int,
        vehicle_type: str,
        version_from: int,
        version_to: int
    ) -> ReportVersionComparison:
        """
        Compare two versions of a report.
        
        Args:
            claim_id: Claim ID
            vehicle_id: Vehicle ID
            vehicle_type: 'client' or 'third_party'
            version_from: Earlier version number
            version_to: Later version number
            
        Returns:
            ReportVersionComparison showing differences
        """
        # Get both versions
        report_from = self.get_specific_version(
            claim_id, vehicle_id, vehicle_type, version_from
        )
        report_to = self.get_specific_version(
            claim_id, vehicle_id, vehicle_type, version_to
        )
        
        # Compare fields
        changes = {}
        comparable_fields = [
            'damage_side', 'area_of_damage', 'type_of_damage',
            'severity', 'confidence_percent', 'total_damaged_points_identified',
            'suggested_repair_action', 'vehicle_status_id'
        ]
        
        for field in comparable_fields:
            old_value = getattr(report_from, field)
            new_value = getattr(report_to, field)
            
            if old_value != new_value:
                changes[field] = {
                    'from': old_value,
                    'to': new_value
                }
        
        # Compare images
        images_from = set(img.file_path for img in report_from.images)
        images_to = set(img.file_path for img in report_to.images)
        
        new_images = images_to - images_from
        removed_images = images_from - images_to
        
        return ReportVersionComparison(
            claim_id=claim_id,
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_type,
            version_from=report_from,
            version_to=report_to,
            changes=changes,
            new_images_count=len(new_images),
            removed_images_count=len(removed_images)
        )
    
    def get_latest_version(
        self,
        claim_id: int,
        vehicle_id: int,
        vehicle_type: str
    ) -> ReportVersionDetail:
        """
        Get the latest version of a report.
        
        Args:
            claim_id: Claim ID
            vehicle_id: Vehicle ID
            vehicle_type: 'client' or 'third_party'
            
        Returns:
            ReportVersionDetail for the latest version
        """
        report = self._get_latest_report(claim_id, vehicle_id, vehicle_type)
        
        if not report:
            raise HTTPException(
                status_code=404,
                detail=f"No reports found for {vehicle_type} vehicle {vehicle_id}"
            )
        
        # Create the base response
        version_detail = ReportVersionDetail.from_orm(report)
        
        # Add upload details and vehicle details for third-party reports
        if vehicle_type == 'third_party':
            uploaded_by_str = report.created_by
            try:
                from libdata.models.tables import User
                if report.created_by:
                    user = self.db.query(User).filter(User.id == report.created_by).first()
                    if user:
                        uploaded_by_str = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email or report.created_by
            except Exception:
                pass

            first_image_name = None
            if report.images and len(report.images) > 0:
                first = report.images[0]
                first_image_name = first.original_filename or (first.file_path.split('/')[-1] if first.file_path else None)

            upload_details = {
                "uploaded_by": uploaded_by_str,
                "file_name": first_image_name,
                "uploaded_on": report.created_at,
                "source": "AI Analysis" if report.raw_result else "User Upload"
            }
            version_detail.upload_details = upload_details
            
            # Get vehicle details from ThirdPartyVehicle
            from libdata.models.tables import ThirdPartyVehicle
            third_party_vehicle = self.db.query(ThirdPartyVehicle).filter(
                ThirdPartyVehicle.id == vehicle_id
            ).first()
            
            if third_party_vehicle:
                vehicle_details = {
                    "vehicle_reg_no": third_party_vehicle.registration,
                    "make_model": f"{third_party_vehicle.make} {third_party_vehicle.model}".strip(),
                    "color": third_party_vehicle.color,
                    "year": None  # ThirdPartyVehicle doesn't have year field
                }
                version_detail.vehicle_details = vehicle_details
        
        # Add upload details and vehicle details for client reports
        if vehicle_type == 'client':
            uploaded_by_str = report.created_by
            try:
                from libdata.models.tables import User
                if report.created_by:
                    user = self.db.query(User).filter(User.id == report.created_by).first()
                    if user:
                        uploaded_by_str = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email or report.created_by
            except Exception:
                pass

            first_image_name = None
            if report.images and len(report.images) > 0:
                first = report.images[0]
                first_image_name = first.original_filename or (first.file_path.split('/')[-1] if first.file_path else None)

            upload_details = {
                "uploaded_by": uploaded_by_str,
                "file_name": first_image_name,
                "uploaded_on": report.created_at,
                "source": "AI Analysis" if report.raw_result else "User Upload"
            }
            version_detail.upload_details = upload_details

            from libdata.models.tables import VehicleDetail
            client_vehicle = self.db.query(VehicleDetail).filter(
                VehicleDetail.id == vehicle_id
            ).first()

            if client_vehicle:
                vehicle_details = {
                    "vehicle_reg_no": client_vehicle.registration,
                    "make_model": f"{client_vehicle.make} {client_vehicle.model}".strip(),
                    "color": client_vehicle.color,
                    "year": None
                }
                version_detail.vehicle_details = vehicle_details
        
        return version_detail
    
    def rollback_to_version(
        self,
        claim_id: int,
        vehicle_id: int,
        vehicle_type: str,
        target_version: int,
        rollback_notes: Optional[str] = None
    ) -> ReportVersionResponse:
        """
        Rollback to a previous version by creating a new version with old data.
        
        This doesn't delete the newer versions - it creates a new version
        that's a copy of the target version.
        
        Args:
            claim_id: Claim ID
            vehicle_id: Vehicle ID
            vehicle_type: 'client' or 'third_party'
            target_version: Version number to rollback to
            rollback_notes: Notes about why rolling back
            
        Returns:
            ReportVersionResponse for the new version
        """
        # Get the target version to rollback to
        target_report = self.get_specific_version(
            claim_id, vehicle_id, vehicle_type, target_version
        )
        
        # Create new version data from target version
        version_data = ReportVersionCreate(
            claim_id=claim_id,
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_type,
            version_notes=rollback_notes or f"Rolled back to version {target_version}",
            damage_side=target_report.damage_side,
            area_of_damage=target_report.area_of_damage,
            type_of_damage=target_report.type_of_damage,
            severity=target_report.severity,
            confidence_percent=target_report.confidence_percent,
            total_damaged_points_identified=target_report.total_damaged_points_identified,
            suggested_repair_action=target_report.suggested_repair_action,
            vehicle_status_id=target_report.vehicle_status_id,
            raw_result=target_report.raw_result,
            images=[img.file_path for img in target_report.images]
        )
        
        return self.create_new_version(version_data)
    
    # Private helper methods
    
    def _get_latest_report(
        self,
        claim_id: int,
        vehicle_id: int,
        vehicle_type: str
    ) -> Optional[VehicleDamageAIReport]:
        """Get the latest version of a report"""
        if vehicle_type == 'client':
            filter_conditions = and_(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.client_vehicle_id == vehicle_id,
                VehicleDamageAIReport.is_latest == True
            )
        else:
            filter_conditions = and_(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.third_party_vehicle_id == vehicle_id,
                VehicleDamageAIReport.is_latest == True
            )
        
        return (
            self.db.query(VehicleDamageAIReport)
            .options(joinedload(VehicleDamageAIReport.images))
            .filter(filter_conditions)
            .first()
        )
    
    def _supersede_report(self, report: VehicleDamageAIReport) -> None:
        """Mark a report as superseded"""
        report.is_latest = False
        report.superseded_at = datetime.utcnow()
        # superseded_by_id will be set when new report is created

    def _resolve_vehicle_status_id(self, status_id: Optional[int], allow_missing: bool = False) -> Optional[int]:
        if status_id is None:
            return None
        if status_id <= 0:
            return None

        exists = (
            self.db.query(VehicleStatus.id)
            .filter(VehicleStatus.id == status_id)
            .scalar()
        )
        if exists is None:
            if allow_missing:
                return None
            raise HTTPException(
                status_code=400,
                detail=f"Vehicle status not found for id={status_id}"
            )

        return status_id
    
    def _lookup_vehicle_status_id(self, label: str) -> int:
        cache_key = label.lower()
        if cache_key in self._status_label_cache:
            return self._status_label_cache[cache_key]

        status_id = (
            self.db.query(VehicleStatus.id)
            .filter(func.lower(VehicleStatus.label) == cache_key)
            .scalar()
        )
        if status_id is None:
            status_id = (
                self.db.query(VehicleStatus.id)
                .order_by(VehicleStatus.sort_order)
                .scalar()
            )
        if status_id is None:
            raise HTTPException(
                status_code=500,
                detail="No vehicle statuses are configured in the system."
            )

        self._status_label_cache[cache_key] = status_id
        return status_id

    @staticmethod
    def _determine_vehicle_status_label(severity: Optional[str]) -> str:
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

    def _determine_vehicle_status_id(
        self,
        severity: Optional[str],
        fallback_status_id: Optional[int]
    ) -> Optional[int]:
        label = self._determine_vehicle_status_label(severity)
        try:
            return self._lookup_vehicle_status_id(label)
        except HTTPException:
            if fallback_status_id is not None:
                return self._resolve_vehicle_status_id(fallback_status_id)
            raise

    def _create_report_version(
        self,
        version_data: ReportVersionCreate,
        version_number: int,
        parent_id: Optional[int],
        previous_status_id: Optional[int]
    ) -> VehicleDamageAIReport:
        """Create a new report version record"""
        # Prepare vehicle ID fields
        if version_data.vehicle_type == 'client':
            client_vehicle_id = version_data.vehicle_id
            third_party_vehicle_id = None
        else:
            client_vehicle_id = None
            third_party_vehicle_id = version_data.vehicle_id
        
        vehicle_status_id = None
        if version_data.vehicle_status_id is not None:
            vehicle_status_id = self._resolve_vehicle_status_id(
                version_data.vehicle_status_id,
                allow_missing=True
            )

        if vehicle_status_id is None:
            vehicle_status_id = self._determine_vehicle_status_id(
                version_data.severity,
                previous_status_id
            )

        new_report = VehicleDamageAIReport(
            claim_id=version_data.claim_id,
            client_vehicle_id=client_vehicle_id,
            third_party_vehicle_id=third_party_vehicle_id,
            version=version_number,
            parent_report_id=parent_id,
            is_latest=True,
            version_notes=version_data.version_notes,
            damage_side=version_data.damage_side,
            area_of_damage=version_data.area_of_damage,
            type_of_damage=version_data.type_of_damage,
            severity=version_data.severity,
            confidence_percent=version_data.confidence_percent,
            total_damaged_points_identified=version_data.total_damaged_points_identified,
            suggested_repair_action=version_data.suggested_repair_action,
            vehicle_status_id=vehicle_status_id,
            raw_result=version_data.raw_result,
            created_by=self.user_id
        )
        
        self.db.add(new_report)
        self.db.flush()  # Get the ID
        
        # Update parent's superseded_by_id
        if parent_id:
            parent_report = self.db.query(VehicleDamageAIReport).get(parent_id)
            if parent_report:
                parent_report.superseded_by_id = new_report.id
        
        return new_report
    
    def _add_images_to_report(
        self,
        report_id: int,
        image_paths: List[str]
    ) -> None:
        """Add images to a report version"""
        for path in image_paths:
            # Extract filename from path
            filename = path.split('/')[-1]
            
            image = VehicleDamageAIImage(
                report_id=report_id,
                file_path=path,
                original_filename=filename,
                created_by=self.user_id
            )
            self.db.add(image)
    
    def _get_vehicle_id(self, claim_id: int, vehicle_type: str) -> int:
        """
        Automatically get vehicle ID based on claim and vehicle type.
        
        Args:
            claim_id: Claim ID
            vehicle_type: 'client' or 'third_party'
            
        Returns:
            Vehicle ID
            
        Raises:
            HTTPException: If vehicle not found
        """
        if vehicle_type == 'client':
            vehicle = (
                self.db.query(VehicleDetail)
                .filter(VehicleDetail.claim_id == claim_id)
                .first()
            )
            if not vehicle:
                raise HTTPException(
                    status_code=404,
                    detail=f"No client vehicle found for claim {claim_id}"
                )
            return vehicle.id
        else:  # third_party
            # Get first third-party vehicle (by sequence)
            vehicle = (
                self.db.query(ThirdPartyVehicle)
                .join(VehicleDetail, ThirdPartyVehicle.client_vehicle_id == VehicleDetail.id)
                .filter(VehicleDetail.claim_id == claim_id)
                .order_by(ThirdPartyVehicle.sequence)
                .first()
            )
            if not vehicle:
                raise HTTPException(
                    status_code=404,
                    detail=f"No third-party vehicle found for claim {claim_id}"
                )
            return vehicle.id
    
    # New methods that automatically detect vehicle ID
    
    def get_version_history_by_claim(
        self,
        claim_id: int,
        vehicle_type: str
    ) -> ReportVersionHistory:
        """Get version history automatically detecting vehicle ID"""
        vehicle_id = self._get_vehicle_id(claim_id, vehicle_type)
        return self.get_version_history(claim_id, vehicle_id, vehicle_type)
    
    def get_specific_version_by_claim(
        self,
        claim_id: int,
        vehicle_type: str,
        version: int
    ) -> ReportVersionDetail:
        """Get specific version automatically detecting vehicle ID"""
        vehicle_id = self._get_vehicle_id(claim_id, vehicle_type)
        return self.get_specific_version(claim_id, vehicle_id, vehicle_type, version)
    
    def get_latest_version_by_claim(
        self,
        claim_id: int,
        vehicle_type: str
    ) -> ReportVersionDetail:
        """Get latest version automatically detecting vehicle ID"""
        vehicle_id = self._get_vehicle_id(claim_id, vehicle_type)
        return self.get_latest_version(claim_id, vehicle_id, vehicle_type)
    
    def compare_versions_by_claim(
        self,
        claim_id: int,
        vehicle_type: str,
        version_from: int,
        version_to: int
    ) -> ReportVersionComparison:
        """Compare versions automatically detecting vehicle ID"""
        vehicle_id = self._get_vehicle_id(claim_id, vehicle_type)
        return self.compare_versions(claim_id, vehicle_id, vehicle_type, version_from, version_to)
    
    def rollback_to_version_by_claim(
        self,
        claim_id: int,
        vehicle_type: str,
        target_version: int,
        rollback_notes: Optional[str] = None
    ) -> ReportVersionResponse:
        """Rollback to version automatically detecting vehicle ID"""
        vehicle_id = self._get_vehicle_id(claim_id, vehicle_type)
        return self.rollback_to_version(claim_id, vehicle_id, vehicle_type, target_version, rollback_notes)

