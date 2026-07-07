from pydantic import BaseModel, Field, field_validator
from typing import Optional
from appflow.models.address import AddressIn, AddressOut

class VehicleOwnerBase(BaseModel):
    gender: Optional[str] = None
    first_name: Optional[str] = None #Field(..., max_length=100)
    surname: Optional[str] = None #Field(..., max_length=100)
    payment_benificiary: Optional[str] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class VehicleOwnerIn(VehicleOwnerBase):
    claim_id: int
    tenant_id: Optional[int] = None
    address: Optional[AddressIn] = None


class VehicleOwnerOut(VehicleOwnerBase):
    id: int
    claim_id: int
    tenant_id: int
    address: Optional[AddressOut] = None

    class Config:
        from_attributes = True
