from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field,field_validator
from appflow.models.address import ContactAddressIn, ContactAddressOut

class ClientMiniIn(BaseModel):
    gender: Optional[str] = None
    first_name: Optional[str] = None
    surname: Optional[str] = None

    address: Optional[ContactAddressIn] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class ClientMiniOut(BaseModel):
    id: Optional[int] = None
    gender: Optional[str] = None
    first_name: Optional[str] = None
    surname: Optional[str] = None

    address: Optional[ContactAddressOut] = None

    class Config:
        from_attributes = True


# Third Party Insurer
class ThirdPartyInsurerBase(BaseModel):
    direct_email: Optional[str] = None
    insurer_reference: Optional[str] = None
    policy_number: Optional[str] = None
    claim_validation: Optional[bool] = None
    handling_reference: Optional[str] = None
    incorrect_mid_reference: Optional[str] = None
    incorrect_acc: Optional[datetime] = None
    initial_eng_made: Optional[datetime] = None
    new_mid: Optional[str] = None
    new_mid_search_ref: Optional[str] = None
    incorrect_reg: Optional[str] = None
    new_mid_search_processed: Optional[bool] = None
    abi_insured: Optional[bool] = None
    liability_accepted_on: Optional[str] = None
    reason_new_mid_id: Optional[int] = None
    liability_stance_id: Optional[int] = None
    settlement_status_id: Optional[int] = None
    handler_id: Optional[int] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class ThirdPartyInsurerIn(ThirdPartyInsurerBase):
    third_party: Optional[ClientMiniIn] = None
    third_party_insurer: Optional[ClientMiniIn] = None
    third_party_handling: Optional[ClientMiniIn] = None
    claim_id: int

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class ThirdPartyInsurerOut(ThirdPartyInsurerBase):
    id: int
    third_party: Optional[ClientMiniOut] = None
    third_party_insurer: Optional[ClientMiniOut] = None
    third_party_handling: Optional[ClientMiniOut] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
