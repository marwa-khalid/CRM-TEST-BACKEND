from pydantic import BaseModel,field_validator
from typing import Optional
from datetime import date
from decimal import Decimal
from libdata.enums import CurrencyTypeEnum


class TotalLossBase(BaseModel):
    currency: CurrencyTypeEnum = CurrencyTypeEnum.GBP
    total_loss_date: Optional[date] = None
    pav: Optional[Decimal] = None
    salvage_amount: Optional[Decimal] = None

    salvage_category_id: Optional[str] = None
    keeping_salvage_id: Optional[str] = None
    pav_agreed_id: Optional[str] = None
    retaining_salvage_id: Optional[str] = None

    engineer_report_sent_tpi: Optional[date] = None
    pav_cheque_received: Optional[date] = None
    pav_sent_client: Optional[date] = None
    vehicle_salvage_milage: Optional[Decimal] = None
    pav_offer_made_client: Optional[date] = None
    pav_offer_accepted: Optional[date] = None
    tpi_instructed_collect_saving_on: Optional[date] = None
    has_salvage_been_collected: Optional[bool] = None
    salvage_collect_on: Optional[date] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class TotalLossIn(TotalLossBase):
    claim_id: int

class TotalLossOut(TotalLossBase):
    id: int
    claim_id: int

    class Config:
        from_attributes = True
