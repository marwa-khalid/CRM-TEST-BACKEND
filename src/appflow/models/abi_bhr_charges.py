from pydantic import BaseModel
from datetime import date
from typing import Optional


class ABIBHRChargesIn(BaseModel):
    claim_id: int
    payment_pack_raised_date: Optional[date] = None
    payment_pack_sent_date: Optional[date] = None
    invoice_number: Optional[str] = None
    date_hire_paid: Optional[date] = None


class ABIBHRChargesOut(ABIBHRChargesIn):
    id: int

    class Config:
        from_attributes = True
