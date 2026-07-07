from typing import Optional
from pydantic import BaseModel, Field,field_validator
from appflow.models.address import ContactAddressIn,ContactAddressOut


class PassengerBase(BaseModel):
    gender: Optional[str] = None
    first_name: Optional[str] = None #Field(..., max_length=100)
    surname: Optional[str] = None #Field(..., max_length=100)


class PassengerIn(PassengerBase):
    claim_id: int
    address: Optional[ContactAddressIn] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class PassengerOut(PassengerBase):
    id: int
    claim_id: int
    tenant_id: int
    address: Optional[ContactAddressOut]

    class Config:
        from_attributes = True