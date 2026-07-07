from datetime import datetime
from typing import Optional,List
from decimal import Decimal
from pydantic import BaseModel,field_validator


class HireDetailBase(BaseModel):
    hire_out: Optional[datetime] = None
    hire_back: Optional[datetime] = None
    no_of_days_hire_so_far: Optional[Decimal] = None
    final_total_no_of_hire_days: Optional[Decimal] = None
    vehicle_file_reference: Optional[str] = None
    # registration_number: Optional[str] = None
    # make: Optional[str] = None
    # model: Optional[str] = None
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
    hire_vehicle_provided_id: int
    claim_id: int

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class HireDetailIn(HireDetailBase):
    pass

class HireDetailListIn(BaseModel):
    hire_details: List[HireDetailIn]


class HireDetailOut(HireDetailBase):
    id: int

    class Config:
        from_attributes = True

class HireDetailListOut(BaseModel):
    hire_details: List[HireDetailOut]
    class Config:
        from_attributes = True

class HireDetailDisplayLabels:
    mapping = {
        "hire_out": "Hire Out",
        "hire_back": "Hire Back",
        "no_of_days_hire_so_far": "Hire So Far",
        "final_total_no_of_hire_days": "Final Hire Days",
        "vehicle_file_reference": "Vehicle File Reference",
        "registration_number": "Registration Number",
        "make": "Make",
        "model": "Model",
        "abi_insurer": "ABI Insurer",
        "abi_hire_charge_per_day": "ABI Hire Charge Per Day",
        "abi_extra_charges_per_day": "ABI Extra Charge Per Day",
        "admin_fee_id": "Admin Fee Type",
        "abi_administration_fee": "ABI Administration Fee",
        "total_abi_hire_charge": "Total ABI Hire Charge",
        "bhr_hire_charge_per_day": "BHR Hire Charge Per Day",
        "bhr_extra_charges_per_day": "BHR Extra Charge Per Day",
        "bhr_administration_fee": "BHR Administration Fee",
        "cdw_charges": "CDW Charges",
        "collection_delivery_fee": "Collection and Delivery Fee",
        "total_bhr_charges": "Total BHR Charges",
    }

    @staticmethod
    def format(field):
        return HireDetailDisplayLabels.mapping.get(field, field.replace("_", " ").title())