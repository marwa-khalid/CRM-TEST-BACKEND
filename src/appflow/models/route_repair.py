from pydantic import BaseModel,field_validator
from typing import Optional
from datetime import date
from decimal import Decimal
from libdata.enums import CurrencyTypeEnum


class RouteRepairBase(BaseModel):
    currency: CurrencyTypeEnum = CurrencyTypeEnum.GBP
    labour: Optional[Decimal] = None
    paint_material: Optional[Decimal] = None
    parts: Optional[Decimal] = None
    miscellaneous: Optional[Decimal] = None
    job_hire: Optional[Decimal] = None
    sub_total: Optional[Decimal] = None
    vat: Optional[Decimal] = None
    total_inc_vat: Optional[Decimal] = None

    cil_total_received: Optional[Decimal] = None
    actual_repair_costs_parts: Optional[Decimal] = None
    actual_repair_costs_labour: Optional[Decimal] = None
    net_cil_amount: Optional[Decimal] = None

    cil_agreed: Optional[bool] = False
    if_roadworthy_cil_fee_agreed: Optional[bool] = False
    agreement_received: Optional[date] = None
    eng_rep_sent_tpi: Optional[date] = None
    cil_cheque_request: Optional[date] = None
    cil_cheque_sent_cl: Optional[date] = None
    cil_removal_confirmation_received: Optional[date] = None

    repair_est_days: Optional[Decimal] = None
    repair_inst: Optional[date] = None
    repair_auth: Optional[date] = None
    estimated_received: Optional[date] = None
    repair_start: Optional[date] = None
    repair_completed: Optional[date] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v


class RouteRepairCreate(RouteRepairBase):
    claim_id: int


class RouteRepairOut(RouteRepairBase):
    id: int
    claim_id: int

    class Config:
        from_attributes = True
