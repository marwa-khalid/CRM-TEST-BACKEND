from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, EmailStr,validator
from libdata.enums import CountryCodeEnum,CurrencyTypeEnum


# ===========================
# Referrer Models
# ===========================
class ReferrerBase(BaseModel):
    company_name: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None
    primary_contact_number : Optional[str] = None
    country : CountryCodeEnum = CountryCodeEnum.UK
    contact_name: Optional[str] = None
    contact_number: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    solicitor: Optional[str] = None
    third_party_capture: Optional[str] = None

    @validator("*", pre=True)
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class ReferrerCreate(ReferrerBase):
    claim_id : Optional[int] = None
    driver_commission: Optional['DriverCommissionCreate'] = None
    referrer_commission: Optional['ReferrerCommissionCreate'] = None

class ReferrerResponse(ReferrerBase):
    id : int
    tenant_id: Optional[int] = None
    driver_commission: Optional['DriverCommissionResponse'] = None
    referrer_commission: Optional['ReferrerCommissionResponse'] = None

    class Config:
        from_attributes = True

class CompanySearchResponse(BaseModel):
    company_name: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str]= None

    class Config:
        orm_mode = True


# ===========================
# Referrer Commission Models
# ===========================
class ReferrerCommissionBase(BaseModel):
    currency : CurrencyTypeEnum = CurrencyTypeEnum.GBP
    on_hire_amount: Optional[Decimal] = None
    on_hire_paid_on: Optional[date] = None
    off_hire_amount: Optional[Decimal] = None
    off_hire_paid_on: Optional[date] = None

    @validator("*", pre=True)
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class ReferrerCommissionCreate(ReferrerCommissionBase):
    pass

class ReferrerCommissionResponse(ReferrerCommissionBase):
    id: int

    class Config:
        from_attributes = True


# ===========================
# Driver Commission Models
# ===========================
class DriverCommissionBase(BaseModel):
    currency : CurrencyTypeEnum = CurrencyTypeEnum.GBP
    on_hire_amount: Optional[Decimal] = None
    on_hire_paid_on: Optional[date] = None
    congestion_charges: Optional[Decimal] = None
    other_charges: Optional[Decimal] = None
    off_hire_amount: Optional[Decimal] = None
    off_hire_paid_on: Optional[date] = None

    @validator("*", pre=True)
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        return v

class DriverCommissionCreate(DriverCommissionBase):
    pass

class DriverCommissionResponse(DriverCommissionBase):
    id: int

    class Config:
        from_attributes = True

#===========================
# Display Labels for History
# ===========================
class ReferrerDisplayLabels:
    labels = {
        # ReferrerBase
        "company_name": "Company Name",
        "address": "Address",
        "postcode": "Postcode",
        "primary_contact_number": "Primary Contact Number",
        "country": "Country",
        "contact_name": "Contact Name",
        "contact_number": "Mobile Number",
        "contact_email": "Email",
        "solicitor": "Solicitor",
        "third_party_capture": "Third Party Capture",
        # DriverCommission
        "on_hire_amount": "Driver On Hire Payment",
        "on_hire_paid_on": "Driver On Hire Paid On",
        "congestion_charges": "Congestion Charges",
        "other_charges": "Other Charges",
        "off_hire_amount": "Driver Off Hire Payment",
        "off_hire_paid_on": "Driver Off Hire Paid On",
        # ReferrerCommission
        "ref_on_hire_amount": "Referrer On Hire Payment Amount",
        "ref_on_hire_paid_on": "Referrer On Hire Paid On",
        "ref_off_hire_amount": "Referrer Off Hire Payment Amount",
        "ref_off_hire_paid_on": "Referrer Off Hire Paid On",
    }

    @classmethod
    def format(cls, field_name: str):
        return cls.labels.get(field_name, field_name.replace("_", " ").title())