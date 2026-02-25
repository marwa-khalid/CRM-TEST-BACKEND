from datetime import date
from pydantic import BaseModel, Field
from typing import Optional

class PoliceDetailBase(BaseModel):
    name: str
    reference_no: str
    station_name: str
    station_address: str
    incident_report_taken: bool
    report_received_date: Optional[date]  # <-- change to date
    additional_info: Optional[str]

class PoliceDetailIn(PoliceDetailBase):
    claim_id : int

class PoliceDetailOut(PoliceDetailBase):
    id: int
    claim_id: int

    class Config:
        from_attributes = True
