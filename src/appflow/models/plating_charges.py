from typing import Optional
from decimal import Decimal
from pydantic import BaseModel


class PlatingChargesIn(BaseModel):
    claim_id: int
    client_vehicle_id: Optional[int] = None
    private_hire_plating_fee: Optional[Decimal] = None
    private_hire_mot_cost: Optional[Decimal] = None
    total_plating_cost: Optional[Decimal] = None
    automatic: Optional[Decimal] = None
    estate: Optional[Decimal] = None
    additional_premium: Optional[Decimal] = None
    additional_driver_charges: Optional[Decimal] = None


class PlatingChargesOut(PlatingChargesIn):
    id: int

    class Config:
        from_attributes = True
