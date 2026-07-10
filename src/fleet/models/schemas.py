"""Pydantic schemas for the Fleet module."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class HireUpdate(BaseModel):
    """Partial update — every field optional so the client can field-level PATCH.
    Only fields explicitly sent are applied (see service, exclude_unset)."""
    # General Details
    file_closed_at: Optional[datetime] = None
    insurance_type: Optional[str] = None
    rental_advisor: Optional[str] = None
    current_position: Optional[str] = None
    bank_name: Optional[str] = None
    account_name: Optional[str] = None
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    # Driver Details
    driver_name: Optional[str] = None
    driver_address: Optional[str] = None
    driver_postcode: Optional[str] = None
    driver_email: Optional[str] = None
    driver_telephone: Optional[str] = None
    driver_mobile: Optional[str] = None
    driving_licence_number: Optional[str] = None
    national_insurance_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    driving_licence_start: Optional[date] = None
    driving_licence_end: Optional[date] = None
    # GDPR & Marketing
    where_found: Optional[str] = None
    privacy_notice_explained: Optional[str] = None
    privacy_notice_date: Optional[date] = None
    privacy_notice_method: Optional[str] = None
    lawful_basis: Optional[str] = None
    email_consent: Optional[str] = None
    email_consent_date: Optional[date] = None
    email_consent_method: Optional[str] = None
    sms_consent: Optional[str] = None
    phone_consent: Optional[str] = None
    postal_consent: Optional[str] = None
    reason_for_withdrawal: Optional[str] = None


class HireDocumentResponse(BaseModel):
    id: int
    doc_type: str
    filename: Optional[str] = None
    file_url: Optional[str] = None
    received_on: Optional[date] = None
    extracted_address: Optional[str] = None

    class Config:
        from_attributes = True


class HireResponse(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    file_opened_at: Optional[datetime] = None
    file_closed_at: Optional[datetime] = None
    insurance_type: Optional[str] = None
    rental_advisor: Optional[str] = None
    current_position: Optional[str] = None
    bank_name: Optional[str] = None
    account_name: Optional[str] = None
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    driver_name: Optional[str] = None
    driver_address: Optional[str] = None
    driver_postcode: Optional[str] = None
    driver_email: Optional[str] = None
    driver_telephone: Optional[str] = None
    driver_mobile: Optional[str] = None
    driving_licence_number: Optional[str] = None
    national_insurance_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    driving_licence_start: Optional[date] = None
    driving_licence_end: Optional[date] = None
    where_found: Optional[str] = None
    privacy_notice_explained: Optional[str] = None
    privacy_notice_date: Optional[date] = None
    privacy_notice_method: Optional[str] = None
    lawful_basis: Optional[str] = None
    email_consent: Optional[str] = None
    email_consent_date: Optional[date] = None
    email_consent_method: Optional[str] = None
    sms_consent: Optional[str] = None
    phone_consent: Optional[str] = None
    postal_consent: Optional[str] = None
    reason_for_withdrawal: Optional[str] = None

    class Config:
        from_attributes = True
