from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from fastapi import Request
from pydantic import BaseModel, Field,field_validator
from libdata.enums import CurrencyTypeEnum,DriverCheckImageType


class DriverCheckBase(BaseModel):
    currency: CurrencyTypeEnum = Field(default=CurrencyTypeEnum.GBP)
    interior_clean_at_check_out: bool = True
    interior_clean_at_check_in: bool = True
    interior_damage_at_check_in: bool = False
    describe_interior_damage: Optional[str] = None

    exterior_clean_at_check_out: bool = True
    exterior_clean_at_check_in: bool = True
    exterior_damage_at_check_in: bool = False
    describe_exterior_damage: Optional[str] = None

    apply_petrol_checkout_charges: bool = False
    petrol_checkout_charges: Optional[Decimal] = None
    petrol_charges_note: Optional[str] = None

    apply_damage_charges: bool = False
    damage_charges: Optional[Decimal] = None
    damage_charges_paid_now: Optional[Decimal] = None
    damage_charges_note: Optional[str] = None

    damage_charges_paid: bool = False
    valet_charges: Optional[Decimal] = None
    total_driver_checkout_charges: Optional[Decimal] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class DriverCheckBulkCreate(BaseModel):
    claim_id: int
    hire_vehicle_provided_id: int
    driver_checks: List[DriverCheckBase]

class DriverCheckImageOut(BaseModel):
    id: int
    driver_check_id: int
    image_type: DriverCheckImageType
    file_path: str
    original_filename: Optional[str]
    created_at: datetime
    url: Optional[str] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj,request: Request = None):
        # Compute the URL when creating the response
        instance = super().from_orm(obj)
        if request:
            base_url = str(request.base_url).rstrip("/")
        else:
            base_url = "http://127.0.0.1:8155"
        # /uploads is mounted on this same app (see main.py), so the image URL is
        # simply <base_url>/uploads/driver-checks<file_path> — no separate port.
        instance.url = f"{base_url}/uploads/driver-checks{instance.file_path}"
        return instance

class DriverCheckOut(DriverCheckBase):
    id: int
    claim_id: int
    hire_vehicle_provided_id: int
    registration_number: Optional[str] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    interior_images: List[DriverCheckImageOut] = []
    exterior_images: List[DriverCheckImageOut] = []

    class Config:
        from_attributes = True

class DriverCheckCreate(DriverCheckBase):
    claim_id: int
    hire_vehicle_provided_id: int

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v
