from pydantic import BaseModel, ConfigDict, Field, field_serializer,validator
from datetime import date, datetime
from typing import Any, Optional, List

class ThirdPartyVehicleCreate(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    registration: Optional[str] = None
    color: Optional[str] = None
    images_available: bool = False
    vehicle_status_id: Optional[int] = None
    damage_area: Optional[str] = None
    unrelated_damage: Optional[str] = None

    @validator("*", pre=True)
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class ThirdPartyVehicleResponse(ThirdPartyVehicleCreate):
    id: int
    client_vehicle_id: int
    sequence: int
    is_active: Optional[bool] = True
    is_deleted: Optional[bool] = False
    ai_reports: List["VehicleDamageAIReportOut"] = []

    class Config:
        from_attributes = True

class BoroughCreate(BaseModel):
    borough_name: Optional[str] = None
    taxi_type_id: Optional[int] = None
    client_badge_number: Optional[str] = None
    badge_expiration_date: Optional[date] = None
    vehicle_badge_number: Optional[str] = None
    any_other_borough: bool = False
    other_borough_name: Optional[str] = None

    @validator("*", pre=True)
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class BoroughResponse(BoroughCreate):
    id: int
    client_vehicle_id: int

    class Config:
        from_attributes = True

class ClientVehicleCreate(BaseModel):
    claim_id: int
    make: Optional[str] = None
    model: Optional[str] = None
    body_type: Optional[str] = None
    registration: Optional[str] = None
    color: Optional[str] = None
    fuel_type_id : Optional[int] = None
    engine_size: Optional[str] = None
    transmission_id : Optional[int] = None
    number_of_seat: Optional[int] = None
    vehicle_category: Optional[str] = None
    vehicle_status_id: Optional[int] = None
    borough: Optional[BoroughCreate] = None
    damage_area: Optional[str] = None
    unrelated_damage: Optional[str] = None
    third_party_vehicles: List[ThirdPartyVehicleCreate] = Field(default_factory=list)

    @validator("*", pre=True)
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class ClientVehicleResponse(ClientVehicleCreate):
    id: int
    claim_id: int
    damage_diagram: Optional[dict] = None
    tenant_id:int
    vehicle_status_id: Optional[int] = None
    borough: Optional[BoroughResponse] = None
    damage_area: Optional[str] = None
    unrelated_damage: Optional[str] = None
    damage_diagram: Optional[dict] = None
    damage_side: Optional[str] = None
    vehicle_status_id: Optional[int] = None
    area_of_damage: Optional[str] = None
    type_of_damage: Optional[str] = None
    severity: Optional[str] = None
    confidence_percent: Optional[int] = None
    total_damaged_points_identified: Optional[int] = None
    suggested_repair_action: Optional[str] = None
    vehicle_status_id: Optional[int] = None
    raw_result: Optional[dict] = None
    third_party_vehicles: List[ThirdPartyVehicleResponse] = []
    ai_reports: List["VehicleDamageAIReportOut"] = []

    class Config:
        from_attributes = True


# ----- Manual damage update payloads -----
class VehicleDamageUpdate(BaseModel):
    id: int
    client_area_of_damage: Optional[str] = None
    client_unrelated_damage: Optional[str] = None
    client_vehicle_status_id: Optional[int] = None
    damage_diagram: Optional[dict] = None

class VehicleDamageBatchUpdate(BaseModel):
    claim_id: int
    vehicle_detail: Optional[VehicleDamageUpdate] = None
    third_party_vehicle_detail: Optional[VehicleDamageUpdate] = None

class VehicleDamageAIImageOut(BaseModel):
    id: int
    file_path: Optional[str] = None
    original_filename: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VehicleDamageAIReportLatestOut(BaseModel):
    id: int
    claim_id: int
    client_vehicle_id: Optional[int] = None
    third_party_vehicle_id: Optional[int] = None

    damage_side: Optional[str] = None
    area_of_damage: Optional[str] = None
    type_of_damage: Optional[str] = None
    severity: Optional[str] = None
    confidence_percent: Optional[int] = None
    total_damaged_points_identified: Optional[int] = None
    suggested_repair_action: Optional[str] = None
    vehicle_status_id: Optional[int] = None

    raw_result: Optional[Any] = None
    report_payload: Optional[Any] = None
    pdf_report_url: Optional[str] = None

    version: Optional[int] = None
    is_latest: Optional[bool] = None
    version_notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None

    images: List[VehicleDamageAIImageOut] = []

    model_config = ConfigDict(from_attributes=True)


class VehicleDamageReportSyncOut(BaseModel):
    report_id: int
    pdf_report_url: str
    message: str

class VehicleDamageAIUpdate(BaseModel):
    id: int
    client_area_of_damage: Optional[str] = None
    client_unrelated_damage: Optional[str] = None
    client_vehicle_status_id: Optional[int] = None
    damage_diagram: Optional[dict] = None
    # AI-specific fields for this vehicle
    damage_side: Optional[str] = None
    area_of_damage: Optional[str] = None
    type_of_damage: Optional[str] = None
    severity: Optional[str] = None
    confidence_percent: Optional[int] = None
    total_damaged_points_identified: Optional[int] = None
    suggested_repair_action: Optional[str] = None
    vehicle_status_id: Optional[int] = None
    raw_result: Optional[dict] = None
    # Per-vehicle image paths
    images: Optional[List[str]] = None

class VehicleDamageAIReportIn(BaseModel):
    claim_id: int
    vehicle_detail: Optional[VehicleDamageAIUpdate] = None
    third_party_vehicle_detail: Optional[VehicleDamageAIUpdate] = None
    # Global AI fields (applied to both vehicles if not specified per vehicle)
    damage_side: Optional[str] = None
    area_of_damage: Optional[str] = None
    type_of_damage: Optional[str] = None
    severity: Optional[str] = None
    confidence_percent: Optional[int] = None
    total_damaged_points_identified: Optional[int] = None
    suggested_repair_action: Optional[str] = None
    vehicle_status_id: Optional[int] = None
    raw_result: Optional[dict] = None
    # Image paths from uploaded files
    images: Optional[List[str]] = None

class VehicleBasicInfo(BaseModel):
    """Basic vehicle information for AI reports"""
    id: int
    make: str
    model: str
    registration: str
    color: Optional[str] = None
    
    class Config:
        from_attributes = True

class ThirdPartyVehicleBasicInfo(BaseModel):
    """Basic third-party vehicle information for AI reports"""
    id: int
    make: str
    model: str
    registration: str
    color: Optional[str] = None
    sequence: int
    
    class Config:
        from_attributes = True

class VehicleDamageAIReportOut(VehicleDamageAIReportIn):
    id: int
    images: List[VehicleDamageAIImageOut] = []
    
    # Vehicle details
    client_vehicle: Optional[VehicleBasicInfo] = None
    third_party_vehicle: Optional[ThirdPartyVehicleBasicInfo] = None
    
    # Audit fields - who uploaded/created the report
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


# ----- Comprehensive Vehicle Damage Report Models -----
class VehicleDamageReportSummary(BaseModel):
    """Summary section of the damage report"""
    total_by_severity: int
    area: str
    estimated_work_category: str

class VehicleDamageReportDetails(BaseModel):
    """Report details section"""
    claim_id: str
    report_id: str
    generated_on: str

class VehicleDamageReportUploadDetails(BaseModel):
    """Upload details section"""
    uploaded_by: str
    file_name: str
    uploaded_on: str
    source: str

class VehicleDamageReportVehicleDetails(BaseModel):
    """Vehicle details section"""
    vehicle_reg_no: str
    make_model: str
    color: str
    year: str

class VehicleDamageReportDetectedDamages(BaseModel):
    """Detected damages section"""
    damage_side: str
    area_of_damage: str
    type_of_damage: str
    severity: str
    confidence_percent: int
    total_damaged_points_identified: int
    ai_suggested_actions: str

class VehicleDamageReportImage(BaseModel):
    """Image in the report"""
    file_path: str
    original_filename: str
    thumbnail_url: Optional[str] = None

class VehicleDamageReportConfirmation(BaseModel):
    """Confirmation details"""
    confirmed_by: str
    confirmed_at: str

class ComprehensiveVehicleDamageReport(BaseModel):

    """Complete vehicle damage report matching the UI format"""
    # Report Details
    report_details: VehicleDamageReportDetails
    
    # Upload Details
    upload_details: VehicleDamageReportUploadDetails
    
    # Vehicle Details
    vehicle_details: VehicleDamageReportVehicleDetails
    
    # Client Unrelated Damage
    client_unrelated_damage: str
    
    # Client Vehicle Status
    client_vehicle_status: str
    
    # Detected Damages
    detected_damages: VehicleDamageReportDetectedDamages
    
    # Uploaded Images
    uploaded_images: List[VehicleDamageReportImage]
    
    # Confirmation
    confirmation: VehicleDamageReportConfirmation
    
    # Summary
    summary: VehicleDamageReportSummary


class VehicleDamageReportSaveResponse(BaseModel):
    id: int
    claim_id: int
    ai_report_id: Optional[int]
    file_name: str
    file_path: str
    s3_key: Optional[str]
    bucket_name: Optional[str]
    report_payload: Optional[dict]

class VehicleDamageReportDataResponse(BaseModel):
    ai_report: Optional[dict]
    pdf_document: Optional[dict]

class VehicleDamageReportUploadMeta(BaseModel):
    claim_id: int
    ai_report_id: Optional[int] = None
    client_vehicle_id: Optional[int] = None
    third_party_vehicle_id: Optional[int] = None
    report_payload: Optional[dict] = None
