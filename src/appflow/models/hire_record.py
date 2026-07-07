from pydantic import BaseModel, field_validator
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional


class HireRecordIn(BaseModel):
    id: Optional[int] = None             # HireVehicleProvided.id (None = create)
    hire_detail_id: Optional[int] = None # HireDetail.id (None = create)

    # HireVehicleProvided fields
    client_vehicle_category_id: Optional[int] = None
    actual_vehicle_category_id: Optional[int] = None
    cross_hire: Optional[bool] = False
    hire_vehicle_status_id: Optional[int] = None
    hire_vehicle_registration: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    hire_start_date: Optional[date] = None
    hire_end_date: Optional[date] = None
    fuel_type: Optional[str] = None
    plate_transfer: Optional[bool] = False

    # HireDetail fields
    vehicle_file_reference: Optional[str] = None
    abi_insurer: Optional[bool] = False
    abi_hire_charge_per_day: Optional[Decimal] = None
    abi_extra_charges_per_day: Optional[Decimal] = None
    admin_fee_id: Optional[int] = None
    abi_administration_fee: Optional[Decimal] = None
    total_abi_hire_charge: Optional[Decimal] = None
    bhr_hire_charge_per_day: Optional[Decimal] = None
    bhr_extra_charges_per_day: Optional[Decimal] = None
    bhr_administration_fee: Optional[Decimal] = None
    cdw_charges: Optional[Decimal] = None
    collection_delivery_fee: Optional[Decimal] = None
    total_bhr_charges: Optional[Decimal] = None
    no_of_days_hire_so_far: Optional[Decimal] = None
    final_total_no_of_hire_days: Optional[Decimal] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class HireRecordsIn(BaseModel):
    claim_id: int
    records: List[HireRecordIn]


class HireRecordOut(BaseModel):
    id: int
    hire_detail_id: Optional[int] = None

    client_vehicle_category_id: Optional[int] = None
    actual_vehicle_category_id: Optional[int] = None
    cross_hire: Optional[bool] = None
    hire_vehicle_status_id: Optional[int] = None
    hire_vehicle_registration: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    hire_start_date: Optional[date] = None
    hire_end_date: Optional[date] = None
    fuel_type: Optional[str] = None
    plate_transfer: Optional[bool] = None

    vehicle_file_reference: Optional[str] = None
    abi_insurer: Optional[bool] = None
    abi_hire_charge_per_day: Optional[Decimal] = None
    abi_extra_charges_per_day: Optional[Decimal] = None
    admin_fee_id: Optional[int] = None
    abi_administration_fee: Optional[Decimal] = None
    total_abi_hire_charge: Optional[Decimal] = None
    bhr_hire_charge_per_day: Optional[Decimal] = None
    bhr_extra_charges_per_day: Optional[Decimal] = None
    bhr_administration_fee: Optional[Decimal] = None
    cdw_charges: Optional[Decimal] = None
    collection_delivery_fee: Optional[Decimal] = None
    total_bhr_charges: Optional[Decimal] = None
    no_of_days_hire_so_far: Optional[Decimal] = None
    final_total_no_of_hire_days: Optional[Decimal] = None

    class Config:
        from_attributes = True
