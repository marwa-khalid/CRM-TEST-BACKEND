from datetime import date
from typing import Optional
from pydantic import BaseModel, EmailStr,Field,field_validator
from appflow.models.address import ContactAddressIn, ContactAddressOut

class PanelSolicitorBase(BaseModel):
    company_name: Optional[str] = Field(..., max_length=200)
    reference: Optional[str] = Field(None, max_length=200)
    recommendation_sent: Optional[date] = None
    note: Optional[str] = Field(None, max_length=500)
    claim_id: int


class PanelSolicitorIn(PanelSolicitorBase):
    email_sent_date: Optional[date]
    accepted_sent_date: Optional[date]= None
    address: Optional[ContactAddressIn]= None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class PanelSolicitorOut(PanelSolicitorBase):
    id: int
    email_sent_date: Optional[date]
    accepted_sent_date: Optional[date]
    address: Optional[ContactAddressOut]

    class Config:
        from_attributes = True

class SolicitorEmailRequest(BaseModel):
    solicitor_email: str
    company_name: str

class SolicitorAcceptedEmailRequest(SolicitorEmailRequest):
    recommendation_date: date