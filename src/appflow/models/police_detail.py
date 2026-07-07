from datetime import date
from pydantic import BaseModel, Field, field_validator
from typing import Optional

class PoliceDetailBase(BaseModel):
    name: Optional[str] = None
    reference_no: Optional[str] = None
    station_name: Optional[str] = None
    station_address: Optional[str] = None
    incident_report_taken: bool = False
    report_received_date: Optional[date] = None  # <-- change to date
    additional_info: Optional[str] = None

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class PoliceDetailIn(PoliceDetailBase):
    claim_id : int

class PoliceDetailOut(PoliceDetailBase):
    id: int
    claim_id: int

    class Config:
        from_attributes = True
