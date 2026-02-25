from typing import Optional, List
from pydantic import BaseModel, Field
from appflow.models.address import ContactAddressIn, ContactAddressOut
from datetime import datetime

class WitnessBase(BaseModel):
    gender: str
    first_name: str = Field(..., max_length=100)
    surname: str = Field(..., max_length=100)
    witness_independent: Optional[bool]


class WitnessIn(WitnessBase):
    claim_id: int
    address: Optional[ContactAddressIn]


class WitnessOut(WitnessBase):
    id: int
    claim_id: int
    tenant_id: int
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

class UpdateQuestionnaireStatusRequest(BaseModel):
    status: str
