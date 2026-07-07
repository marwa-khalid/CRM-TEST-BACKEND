from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional
from libdata.enums import WeatherTypeEnum


class AccidentDetailBase(BaseModel):
    date_time: Optional[datetime] = None
    condition: Optional[int]=None
    location: Optional[str] = None #Field(..., max_length=255)
    description: Optional[str] = None
    service_date_time: Optional[datetime] = None
    any_passenger: bool = False
    passenger_no: Optional[int] = None
    witness: bool = False
    police_attend: bool = False
    dash_footage: bool = False

    @field_validator("*", mode="before")
    def empty_to_none(cls, v):
        if v == "":
            return None
        return v

class AccidentDetailIn(AccidentDetailBase):
    claim_id: int

class AccidentDetailOut(AccidentDetailBase):
    id: int
    claim_id: int
    tenant_id: Optional[int]

    class Config:
        from_attributes = True

class AccidentDisplayLabels:
    labels = {
        "date_time": "Accident Date/Time",
        "condition": "Weather Condition",
        "location": "Location",
        "description": "Version of Events",
        "service_date_time": "Service Date/Time",
        "any_passenger": "Any Passenger?",
        "passenger_no": "Number of Passengers",
        "witness": "Any Witness?",
        "police_attend": "Did Police Attend?",
        "dash_footage": "Dash Cam Footage"
    }

    @classmethod
    def format(cls, field_name: str) -> str:
        return cls.labels.get(field_name, field_name.replace("_", " ").title())
