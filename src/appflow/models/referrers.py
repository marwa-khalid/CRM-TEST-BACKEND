from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, EmailStr
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

class ReferrerCreate(ReferrerBase):
    claim_id : Optional[int]=None
    driver_commission: Optional['DriverCommissionCreate']=None
    referrer_commission: Optional['ReferrerCommissionCreate']=None

class ReferrerResponse(ReferrerBase):
    id : int
    tenant_id: Optional[int] = None
    driver_commission: Optional['DriverCommissionResponse']= None
    referrer_commission: Optional['ReferrerCommissionResponse']=None

    class Config:
        orm_mode = True

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
    on_hire_amount: Optional[Decimal]= None
    on_hire_paid_on: Optional[date] = None
    off_hire_amount: Optional[Decimal] = None
    off_hire_paid_on: Optional[date] = None

class ReferrerCommissionCreate(ReferrerCommissionBase):
    pass

class ReferrerCommissionResponse(ReferrerCommissionBase):
    id: int

    class Config:
        orm_mode = True


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

class DriverCommissionCreate(DriverCommissionBase):
    pass

class DriverCommissionResponse(DriverCommissionBase):
    id: int

    class Config:
        orm_mode = True
