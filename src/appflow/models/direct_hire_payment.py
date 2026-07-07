from pydantic import BaseModel
from typing import Optional
from datetime import date


class DirectHirePaymentIn(BaseModel):
    claim_id: int
    date_settlement_received: Optional[date] = None
    settlement_amount_received: Optional[float] = None


class DirectHirePaymentOut(DirectHirePaymentIn):
    id: int

    class Config:
        from_attributes = True


class DirectHirePaymentGetOut(BaseModel):
    saved: Optional[DirectHirePaymentOut] = None
