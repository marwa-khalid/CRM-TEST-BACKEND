from pydantic import BaseModel,Field
from datetime import date
from typing import Optional, List

class ThirdPartyVehicleCreate(BaseModel):
    make:Optional[str] = None
    model:Optional[str] = None
    registration:Optional[str] = None
    color: Optional[str] = None
    images_available: bool = False

class ThirdPartyVehicleResponse(ThirdPartyVehicleCreate):
    id:Optional[int] = None
    client_vehicle_id: Optional[int] = None
    sequence: Optional[int] = None

    class Config:
        orm_mode = True

class BoroughCreate(BaseModel):
    borough_name:Optional[str] = None
    taxi_type_id: Optional[int] = None
    client_badge_number:Optional[str] = None
    badge_expiration_date:Optional[date] = None
    vehicle_badge_number:Optional[str] = None
    any_other_borough: bool = False
    other_borough_name: Optional[str] = None

class BoroughResponse(BoroughCreate):
    id:Optional[int] = None
    client_vehicle_id: Optional[int] = None

    class Config:
        orm_mode = True

class ClientVehicleCreate(BaseModel):
    claim_id:Optional[int] = None
    make:Optional[str] = None
    model:Optional[str] = None
    body_type:Optional[str] = None
    registration:Optional[str] = None
    color: Optional[str] = None
    fuel_type_id : Optional[int] = None
    engine_size:Optional[str] = None
    transmission_id : Optional[int] = None
    number_of_seat: Optional[int] = None
    vehicle_category: Optional[str] = None
    borough: Optional[BoroughCreate] = None
    third_party_vehicles: List[ThirdPartyVehicleCreate] = Field(default_factory=list)

class ClientVehicleResponse(ClientVehicleCreate):
    id:Optional[int] = None
    claim_id:Optional[int] = None
    tenant_id:Optional[int] = None
    borough: Optional[BoroughResponse] = None
    third_party_vehicles: List[ThirdPartyVehicleResponse] = []

    class Config:
        orm_mode = True