from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class AccidentDetailBase(BaseModel):
    date_time: Optional[datetime]=None
    condition:Optional[int]=None
    location: Optional[str] = None,Field(..., max_length=255)
    description: Optional[str] = None
    service_date_time: Optional[datetime] =None
    any_passenger: bool = False
    passenger_no: Optional[int]
    witness: bool = False
    police_attend: bool = False
    dash_footage: bool = False


class AccidentDetailIn(AccidentDetailBase):
    claim_id: int

class AccidentDetailOut(AccidentDetailBase):
    id: int
    claim_id: int
    tenant_id: Optional[int]

    class Config:
        from_attributes = True
