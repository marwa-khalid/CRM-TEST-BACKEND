from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional
from appflow.models.address import AddressIn, AddressOut
from libdata.enums import CountryCodeEnum

class ClientDetailBase(BaseModel):
    # Basic info
    gender: Optional[str] = None
    # Changed Field(...) to Field(None, ...) to allow null/missing
    first_name: Optional[str] = Field(None, max_length=100)
    surname: Optional[str] = Field(None, max_length=100)
    age: Optional[int] = 0
    occupation: Optional[str] = None
    date_of_birth: Optional[date] = None
    ni_number: Optional[str] = None
    country: CountryCodeEnum = CountryCodeEnum.UK

    # Driving details
    driver_code: Optional[str] = None
    day_driver: bool = True 
    driver_base: Optional[str] = None

    # Bank details
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    bank_details_note: Optional[str] = None

    # Flags
    ci_vat_registered: bool = False
    is_vulnerable: bool = False
    vulnerable_note: Optional[str] = None

    # Contact details
    # Set a default for language_id if it can be missing
    language_id: Optional[int] = None 
    speaks_clear_english: bool = True
    contact_via_alternative_person: bool = False
    alter_person: Optional[str] = None
    alter_number: Optional[str] = None

class ClientDetailIn(ClientDetailBase):
    claim_id: int
    tenant_id: Optional[int] = None
    address: Optional[AddressIn] = None
    language_id: Optional[int] = None
    language: Optional[str] = None

class ClientDetailOut(ClientDetailBase):
    id: int
    claim_id: int
    tenant_id:  Optional[int] = None
    address: Optional[AddressOut]
    language_id: Optional[int]

    class Config:
        from_attributes = True
