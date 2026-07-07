from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import List, Optional

class HireVehicleProvidedSectionAIn(BaseModel):
    inst_fleet_on_hire: Optional[datetime] = None
    inst_fleet_off_hire: Optional[datetime] = None
    hire_vehicle_check_sheet: Optional[datetime] = None
    recovery_storage: Optional[datetime] = None
    mitigation_questionnaire: Optional[datetime] = None
    hire_documentation: Optional[datetime] = None
    fee_exemption_form: Optional[datetime] = None
    send_licensing_document_account: Optional[datetime] = None
    request_updated_insurance_schedule: Optional[datetime] = None
    raise_authority_letter: Optional[datetime] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class HireVehicleProvidedSectionBIn(BaseModel):
    client_vehicle_category_id: Optional[int] = None
    actual_vehicle_category_id: Optional[int] = None
    cross_hire: Optional[bool] = False
    hire_vehicle_status_id: Optional[int] = None
    provider_name: Optional[str] = None
    contact_number: Optional[str] = None
    rate: Optional[float] = None
    hire_vehicle_registration: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    hire_start_date: Optional[date] = None
    hire_end_date: Optional[date] = None
    fuel_type: Optional[str] = None
    plate_transfer: Optional[bool] = False

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class HireVehicleProvidedIn(BaseModel):
    claim_id: int
    section_a: HireVehicleProvidedSectionAIn
    section_b: List[HireVehicleProvidedSectionBIn]

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class HireVehicleProvidedOut(BaseModel):
    # --- Common fields ---
    id: int
    claim_id: int
    client_vehicle_category_id: Optional[int] = None
    actual_vehicle_category_id: Optional[int] = None
    cross_hire: Optional[bool]
    hire_vehicle_status_id: Optional[int]
    provider_name: Optional[str]
    contact_number: Optional[str]
    rate: Optional[float]
    hire_vehicle_registration: Optional[str]
    make: Optional[str]
    model: Optional[str]
    hire_start_date: Optional[date]
    hire_end_date: Optional[date]
    fuel_type: Optional[str]
    plate_transfer: Optional[bool]
    is_active: Optional[bool]

    # --- Section A fields ---
    inst_fleet_on_hire: Optional[datetime] = None
    inst_fleet_off_hire: Optional[datetime] = None
    hire_vehicle_check_sheet: Optional[datetime] = None
    recovery_storage: Optional[datetime] = None
    mitigation_questionnaire: Optional[datetime] = None
    hire_documentation: Optional[datetime] = None
    fee_exemption_form: Optional[datetime] = None
    send_licensing_document_account: Optional[datetime] = None
    request_updated_insurance_schedule: Optional[datetime] = None
    raise_authority_letter: Optional[datetime] = None

    # --- Audit fields ---
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None

    class Config:
        from_attributes = True

class SectionBVehicleOut(BaseModel):
    make: str | None = None
    model: str | None = None
    hire_vehicle_registration: str | None = None
    hire_start_date: date | None = None
    hire_end_date: date | None = None

    class Config:
        from_attributes = True

class HireVehicleProvidedSectionBUpdateIn(BaseModel):
    id: Optional[int] = None

    client_vehicle_category_id: Optional[int] = None
    actual_vehicle_category_id: Optional[int] = None
    cross_hire: Optional[bool] = False
    hire_vehicle_status_id: Optional[int] = None
    provider_name: Optional[str] = None
    contact_number: Optional[str] = None
    rate: Optional[float] = None
    hire_vehicle_registration: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    hire_start_date: Optional[date] = None
    hire_end_date: Optional[date] = None
    fuel_type: Optional[str] = None
    plate_transfer: Optional[bool] = False

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class HireVehicleProvidedUpdateIn(BaseModel):
    claim_id: int
    section_a: HireVehicleProvidedSectionAIn
    section_b: List[HireVehicleProvidedSectionBUpdateIn]

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v
