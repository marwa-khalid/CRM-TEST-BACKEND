from pydantic import BaseModel, Field,field_validator
from typing import Optional


class AddressBase(BaseModel):
    address: Optional[str] = None #Field(..., max_length=255)
    postcode: Optional[str] = None #Field(..., max_length=20)
    home_tel: Optional[str] =None
    mobile_tel: Optional[str] = None #Field(..., max_length=20)
    email: Optional[str] = None#Field(..., max_length=100)

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class AddressIn(AddressBase):
    pass


class AddressOut(AddressBase):
    id: int

    class Config:
        from_attributes = True

class ContactAddressIn(BaseModel):
    address: Optional[str] = None
    postcode: Optional[str] = None
    landline_tel: Optional[str] = None
    mobile_tel: Optional[str] = None
    email: Optional[str] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class ContactAddressOut(ContactAddressIn):
    id: int

    class Config:
        from_attributes = True