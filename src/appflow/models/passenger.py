from typing import Optional
from pydantic import BaseModel, Field
from appflow.models.address import ContactAddressIn,ContactAddressOut


class PassengerBase(BaseModel):
    gender: str
    first_name: str = Field(..., max_length=100)
    surname: str = Field(..., max_length=100)


class PassengerIn(PassengerBase):
    claim_id: int
    address: Optional[ContactAddressIn] = None


class PassengerOut(PassengerBase):
    id: int
    claim_id: int
    tenant_id: int
    address: Optional[ContactAddressOut]

    class Config:
        from_attributes = True