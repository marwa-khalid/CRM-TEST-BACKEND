from pydantic import BaseModel, Field, field_validator
from typing import Optional
from decimal import Decimal
from libdata.enums import CurrencyTypeEnum
from appflow.models.address import ContactAddressIn, ContactAddressOut


class InsurerBrokerBase(BaseModel):
    company_name: Optional[str] = None
    reference: Optional[str] = None
    policy_number: Optional[str] = None
    policy_holder: Optional[str] = None
    policy_type_id: Optional[int] = None
    number_of_additional_driver: Optional[int] = None
    number_vehicle_on_policy: Optional[int] = None
    number_vehicle_in_use: Optional[int] = None
    policy_cover_id: Optional[int] = None
    currency: CurrencyTypeEnum = CurrencyTypeEnum.GBP
    policy_cover_excess: Optional[Decimal] = None
    sdp: bool = False
    private_hire: bool = False
    claim_id: int

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class InsurerBrokerIn(InsurerBrokerBase):
    address: Optional[ContactAddressIn] = None


class InsurerBrokerOut(InsurerBrokerBase):
    id: int
    address: Optional[ContactAddressOut]

    class Config:
        from_attributes = True