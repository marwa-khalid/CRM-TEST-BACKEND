from datetime import date
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel,EmailStr,field_validator
from libdata.enums import CurrencyTypeEnum
from appflow.models.address import ContactAddressIn,ContactAddressOut



class EngineerDetailBase(BaseModel):
    company_name: Optional[str] = None
    vehicle_payment_beneficiary: Optional[str] = None
    reference: Optional[str] = None

    currency: CurrencyTypeEnum = CurrencyTypeEnum.GBP
    actual_fee: Optional[Decimal] = None
    invoice_received_on: Optional[date] = None
    invoice_paid_on: Optional[date] = None
    invoice_settled_on: Optional[date] = None
    invoice_settled_amount: Optional[Decimal] = None

    engineer_report_received: bool = False
    engineer_instructed: Optional[date] = None
    inspection_date: Optional[date] = None
    engineer_report_received_date: Optional[date] = None
    engineer_fee: Optional[Decimal] = None

    site: Optional[str] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class EngineerDetailCreate(EngineerDetailBase):
    claim_id: int
    engineer_address: ContactAddressIn
    vehicle_address: Optional[ContactAddressIn] = None


class EngineerDetailOut(EngineerDetailBase):
    id: int
    claim_id: int
    tenant_id: int
    engineer_address: ContactAddressOut
    vehicle_address: Optional[ContactAddressOut] = None

    class Config:
        from_attributes = True

class EngineerEmailRequest(BaseModel):
    engineer_email: str
    engineer_company: str
    engineer_address: str
    engineer_postcode: str
    current_location: str