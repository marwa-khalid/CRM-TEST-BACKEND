from typing import Optional, List
from pydantic import BaseModel, Field,field_validator
from appflow.models.address import ContactAddressIn, ContactAddressOut
from datetime import datetime

class WitnessBase(BaseModel):
    gender: Optional[str] = None
    first_name: Optional[str] = None #Field(..., max_length=100)
    surname: Optional[str] = None #Field(..., max_length=100)
    witness_independent: Optional[bool] = False


class WitnessIn(WitnessBase):
    claim_id: int
    address: Optional[ContactAddressIn] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class WitnessOut(WitnessBase):
    id: int
    claim_id: int
    tenant_id: Optional[int] = None
    address: Optional[ContactAddressOut]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WitnessEmailRequest(BaseModel):
    witness_email: str
    witness_name: str
    reference: str
    option: str  # "pdf" or "link"
    witness_id: Optional[int] = None


class QuestionnaireAnswer(BaseModel):
    question: str
    answer: str


class QuestionnaireSubmitRequest(BaseModel):
    status: Optional[str] = None
    witness_sign: Optional[str] = None
    officer_sign: Optional[str] = None
    witness_name: Optional[str] = None
    officer_name: Optional[str] = None
    date_of_witness: Optional[datetime] = None
    date_of_officer: Optional[datetime] = None
    answers: List[QuestionnaireAnswer]

    witness_statement: Optional[str] = None
    pdf_base64: Optional[str] = None
    pdf_filename: Optional[str] = "Witness-Questionnaire.pdf"

class UpdateQuestionnaireStatusRequest(BaseModel):
    status: str


class WitnessDownloadRequest(BaseModel):
    witness_name: str
    reference: str
    witness_address: Optional[str] = None
    witness_dob: Optional[str] = None
    witness_occupation: Optional[str] = None
