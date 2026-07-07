from datetime import date
from decimal import Decimal
from typing import Optional,List
from pydantic import BaseModel,EmailStr,field_validator
from libdata.enums import CurrencyTypeEnum
from appflow.models.address import ContactAddressIn,ContactAddressOut


class StorageBase(BaseModel):
    storage_provider: Optional[str] = None
    name: Optional[str] = None
    claim_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_storage_days: Optional[int] = None
    currency: CurrencyTypeEnum = CurrencyTypeEnum.GBP
    charge_per_day: Optional[Decimal] = None
    total_storage_charges: Optional[Decimal] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class StorageIn(StorageBase):
    address: Optional[ContactAddressIn] = None

class StorageOut(StorageBase):
    id: int
    address: ContactAddressOut
    class Config:
        from_attributes = True

class RecoveryBase(BaseModel):
    recovery_provider: Optional[str] = None
    name: Optional[str] = None
    claim_id: Optional[int] = None
    date_of_recovery: Optional[date] = None
    currency: CurrencyTypeEnum = CurrencyTypeEnum.GBP
    recovery_charges: Optional[Decimal] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class RecoveryIn(RecoveryBase):
    address: Optional[ContactAddressIn] = None


class RecoveryOut(RecoveryBase):
    id: int
    address: ContactAddressOut

    class Config:
        from_attributes = True

class StorageRecoveryIn(BaseModel):
    storages: List[StorageIn]
    recoveries: List[RecoveryIn]

class StorageRecoveryOut(BaseModel):
    storages: List[StorageOut]
    recoveries: List[RecoveryOut]

class StorageUpdate(StorageIn):
    id: Optional[int] = None

class RecoveryUpdate(RecoveryIn):
    id: Optional[int] = None

class StorageRecoveryUpdateIn(BaseModel):
    storages: Optional[List[StorageUpdate]] = None
    recoveries: Optional[List[RecoveryUpdate]] = None

class StorageRecoveryUpdateOut(BaseModel):
    storages: Optional[List[StorageOut]] = None
    recoveries: Optional[List[RecoveryOut]] = None