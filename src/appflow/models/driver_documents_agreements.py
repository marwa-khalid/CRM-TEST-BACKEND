from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, ConfigDict


class DriverDocumentAgreementBase(BaseModel):
    # Section 1: Driver Proofs Check List
    driver_license_received_on: Optional[datetime] = None
    driver_license_file_url: Optional[str] = None

    license_checks_completed_on: Optional[datetime] = None
    license_checks_completed_file_url: Optional[str] = None

    proof_of_address_1_received_on: Optional[datetime] = None
    proof_of_address_1_file_url: Optional[str] = None

    proof_of_address_2_received_on: Optional[datetime] = None
    proof_of_address_2_file_url: Optional[str] = None

    pre_hire_bank_statement_received_on: Optional[datetime] = None
    pre_hire_bank_statement_file_url: Optional[str] = None

    post_hire_bank_statement_received_on: Optional[datetime] = None
    post_hire_bank_statement_file_url: Optional[str] = None

    taxi_badge_received_on: Optional[datetime] = None
    taxi_badge_file_url: Optional[str] = None

    v5_received_on: Optional[datetime] = None
    v5_file_url: Optional[str] = None

    mot_certificate_received_on: Optional[datetime] = None
    mot_certificate_file_url: Optional[str] = None

    insurance_certificate_received_on: Optional[datetime] = None
    insurance_certificate_file_url: Optional[str] = None

    suspension_notice_received_on: Optional[datetime] = None
    suspension_notice_file_url: Optional[str] = None

    suspension_uplift_received_on: Optional[datetime] = None
    suspension_uplift_file_url: Optional[str] = None

    # Section 2: Agreements & Statements
    signed_cha_received_on: Optional[datetime] = None
    signed_cha_file_url: Optional[str] = None

    signed_mitigation_received_on: Optional[datetime] = None
    signed_mitigation_file_url: Optional[str] = None

    arf_received_on: Optional[datetime] = None
    arf_file_url: Optional[str] = None

    signed_cil_agreement_received_on: Optional[datetime] = None
    signed_cil_agreement_file_url: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class DriverDocumentAgreementCreate(DriverDocumentAgreementBase):
    claim_id: int


class DriverDocumentAgreementOut(DriverDocumentAgreementBase):
    id: int
    claim_id: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DriverDocumentUploadOut(BaseModel):
    field_name: str
    file_url: str
    uploaded_at: datetime