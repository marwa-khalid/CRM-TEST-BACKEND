from pydantic import BaseModel
from typing import Optional
from datetime import date


class HirePaymentDetailsIn(BaseModel):
    claim_id: int
    payment_amount: Optional[float] = None
    received_date: Optional[date] = None
    payment_reason: Optional[str] = None
    payments_received_total: Optional[float] = None
    write_off_amount: Optional[float] = None
    payment_outstanding_incl_vat: Optional[float] = None
    payment_outstanding_excl_vat: Optional[float] = None


class HirePaymentDetailsOut(HirePaymentDetailsIn):
    id: int

    class Config:
        from_attributes = True


class HirePaymentDetailsGetOut(BaseModel):
    saved: Optional[HirePaymentDetailsOut] = None
