from pydantic import BaseModel, Field
from typing import Optional


class AddressBase(BaseModel):
    address: Optional[str] = Field(..., max_length=255)
    postcode: Optional[str] = Field(..., max_length=20)
    home_tel: Optional[str]
    mobile_tel: Optional[str] = Field(..., max_length=20)
    email: Optional[str] = Field(..., max_length=100)


class AddressIn(AddressBase):
    pass


class AddressOut(AddressBase):
    id: int

    class Config:
        from_attributes = True

class ContactAddressIn(BaseModel):
    address: Optional[str] = Field(..., max_length=255)
    postcode: Optional[str] = Field(..., max_length=20)
    mobile_tel: Optional[str] = Field(..., max_length=20)
    email: Optional[str] = Field(..., max_length=100)

class ContactAddressOut(ContactAddressIn):
    id: int

    class Config:
        from_attributes = True