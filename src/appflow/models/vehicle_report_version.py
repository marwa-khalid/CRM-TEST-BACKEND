"""
Pydantic models for vehicle damage report versioning
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from appflow.models.vehicle_detail import VehicleDamageAIImageOut


class ReportVersionCreate(BaseModel):
    """Create a new version of a damage report"""
    claim_id: int
    vehicle_id: int
    vehicle_type: str = Field(..., description="'client' or 'third_party'")
    version_notes: Optional[str] = Field(None, description="Notes about what changed in this version")
    
    # AI Analysis fields
    damage_side: Optional[str] = None
    area_of_damage: Optional[str] = None
    type_of_damage: Optional[str] = None
    severity: Optional[str] = None
    confidence_percent: Optional[int] = None
    total_damaged_points_identified: Optional[int] = None
    suggested_repair_action: Optional[str] = None
    vehicle_status_id: Optional[int] = None
    raw_result: Optional[dict] = None
    
    # New images for this version
    images: List[str] = Field(default_factory=list, description="Paths to new images")


class ReportVersionSummary(BaseModel):
    """Summary information about a report version"""
    id: int
    version: int
    created_at: datetime
    created_by: Optional[int] = None
    is_latest: bool
    version_notes: Optional[str] = None
    image_count: int
    superseded_at: Optional[datetime] = None
    
    # Key damage metrics for quick comparison
    confidence_percent: Optional[int] = None
    severity: Optional[str] = None
    total_damaged_points: Optional[int] = None
    
    class Config:
        from_attributes = True


class ReportVersionDetail(BaseModel):
    """Detailed information about a specific report version"""
    id: int
    version: int
    claim_id: int
    client_vehicle_id: Optional[int] = None
    third_party_vehicle_id: Optional[int] = None
    
    # Version tracking
    parent_report_id: Optional[int] = None
    is_latest: bool
    version_notes: Optional[str] = None
    superseded_at: Optional[datetime] = None
    superseded_by_id: Optional[int] = None
    
    # AI Analysis
    damage_side: Optional[str] = None
    area_of_damage: Optional[str] = None
    type_of_damage: Optional[str] = None
    severity: Optional[str] = None
    confidence_percent: Optional[int] = None
    total_damaged_points_identified: Optional[int] = None
    suggested_repair_action: Optional[str] = None
    vehicle_status_id: Optional[int] = None
    raw_result: Optional[dict] = None
    
    # Images for this version
    images: List[VehicleDamageAIImageOut] = []
    
    # Upload/Created by details
    upload_details: Optional[dict] = None
    
    # Vehicle details
    vehicle_details: Optional[dict] = None
    
    # Audit fields
    created_at: datetime
    created_by: Optional[int] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None
    
    class Config:
        from_attributes = True


class ReportVersionHistory(BaseModel):
    """Complete version history for a vehicle's damage reports"""
    claim_id: int
    vehicle_id: int
    vehicle_type: str  # 'client' or 'third_party'
    total_versions: int
    latest_version: int
    versions: List[ReportVersionSummary]
    
    class Config:
        from_attributes = True


class ReportVersionComparison(BaseModel):
    """Compare two versions of a report"""
    claim_id: int
    vehicle_id: int
    vehicle_type: str
    
    version_from: ReportVersionDetail
    version_to: ReportVersionDetail
    
    changes: dict = Field(
        description="Dictionary of changed fields with before/after values"
    )
    new_images_count: int
    removed_images_count: int
    
    class Config:
        from_attributes = True


class ReportVersionResponse(BaseModel):
    """Response after creating a new version"""
    success: bool
    message: str
    new_version: int
    report_id: int
    previous_version: Optional[int] = None
    changes_summary: Optional[str] = None

