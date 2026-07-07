from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import Optional
from appflow.models.address import AddressIn, AddressOut
from libdata.enums import CountryCodeEnum

class ClientDetailBase(BaseModel):
    # Basic info
    gender: Optional[str] = None
    first_name: Optional[str] = None
    surname: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    date_of_birth: Optional[date] = None
    ni_number: Optional[str] = None
    country : CountryCodeEnum = CountryCodeEnum.UK

    # Driving details
    driver_code: Optional[str]
    day_driver: bool = True  # True=Day, False=Night
    driver_base: Optional[str]

    # Bank details
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    bank_details_note: Optional[str] = None

    # Flags
    ci_vat_registered: bool = False
    is_vulnerable: bool = False
    vulnerable_note: Optional[str]

    # Dependents & caring
    dependents: Optional[str] = None
    partner: Optional[bool] = None
    children: Optional[str] = None
    caring_for_elderly: Optional[bool] = None
    dependents_details: Optional[str] = None

    # Bank details extended
    pay_notification_date: Optional[date] = None

    # Contact details
    # language_id : int
    other_language: Optional[str] = None  # free-text when language is "Other"
    speaks_clear_english: bool = True
    contact_via_alternative_person: bool = False
    alter_person: Optional[str]
    alter_number: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ClientDetailIn(ClientDetailBase):
    claim_id: int
    tenant_id: Optional[int] = None
    address: Optional[AddressIn] = None
    language_id: Optional[int] = None
    # language: Optional[str] = None
    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class ClientDetailOut(ClientDetailBase):
    id: int
    claim_id: int
    tenant_id: int
    address: Optional[AddressOut]
    language_id: Optional[int]

    class Config:
        from_attributes = True

class ClientDisplayLabels:
    labels = {
        "gender": "Gender",
        "first_name": "First Name",
        "surname": "Surname",
        "age": "Age",
        "occupation": "Occupation",
        "date_of_birth": "Date of Birth",
        "ni_number": "NI Number",
        "country": "Country",
        "driver_code": "Driver Code",
        "day_driver": "Day/Night Driver",
        "driver_base": "Driver Base",
        "sort_code": "Sort Code",
        "account_number": "Account Number",
        "bank_details_note": "Pay Driver Notes",
        "pay_notification_date": "Pay Notification Date",
        "ci_vat_registered": "CI VAT Registered",
        "is_vulnerable": "Is Vulnerable",
        "vulnerable_note": "Vulnerable Note(Why?)",
        "language_id": "Language",
        "other_language": "Other Language",
        "speaks_clear_english": "Does the client speak clear english?",
        "contact_via_alternative_person": "Contact via Alternative Person",
        "alter_person": "Contact Name",
        "alter_number": "Contact Telephone",
    }

    @classmethod
    def format(cls, field_name: str):
        return cls.labels.get(field_name, field_name.replace("_", " ").title())

class AddressDisplayLabels:
    labels = {
        "address": "Address",
        "postcode": "Postcode",
        "home_tel": "Home Telephone",
        "mobile_tel": "Mobile Number",
        "email": "Email"
    }

    EXCLUDE_FIELDS = {"id", "created_at", "updated_at"}

    @classmethod
    def format(cls, field_name: str) -> str:
        return cls.labels.get(field_name, field_name.replace("_", " ").title())

