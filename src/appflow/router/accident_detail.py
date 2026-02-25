# appflow/routers/location_conditions.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from libdata.settings import get_session
from appflow.utils import get_tenant_id
from appflow.services.accident_service import AccidentService
from appflow.models.accident_detail import AccidentDetailIn, AccidentDetailOut

from appflow.models.passenger import PassengerOut, PassengerIn

from appflow.models.police_detail import PoliceDetailOut, PoliceDetailIn
from appflow.models.witness import WitnessOut, WitnessIn

accident_router = APIRouter(prefix="/accident-details", tags=["accidents"])


@accident_router.post("/", response_model=AccidentDetailOut, status_code=status.HTTP_201_CREATED)
def create_accident_location(
    request: Request,
    accident_data: AccidentDetailIn,
    db: Session = Depends(get_session)
):
    tenant_id = get_tenant_id(request)
    return AccidentService.create_location_condition(db, accident_data, tenant_id)

@accident_router.get("/", response_model=List[AccidentDetailOut])
def get_all_accident_location(
    claim_id: int = None,
    db: Session = Depends(get_session)
):
    return AccidentService.get_all_location_conditions(db, claim_id)

@accident_router.get("/{id}", response_model=AccidentDetailOut)
def get_accident_location(
    id: int,
    db: Session = Depends(get_session)
):
    return AccidentService.get_location_condition_by_id(db, id)

@accident_router.get("/accident/{claim_id}", response_model=AccidentDetailOut)
def get_accident_by_claim(
    claim_id: int,
    db: Session = Depends(get_session)
):
    return AccidentService.get_location_condition_by_claim(db, claim_id)

@accident_router.put("/{claim_id}", response_model=AccidentDetailOut)
def update_accident_location(
    claim_id: int,
    data: AccidentDetailIn,
    db: Session = Depends(get_session)
):
    return AccidentService.update_location_condition(db, claim_id, data)

@accident_router.patch("/{id}", response_model=AccidentDetailOut)
def deactivate_location_condition(
    id: int,
    db: Session = Depends(get_session)
):
    return AccidentService.deactivate_location_condition(db, id)

@accident_router.post("/passenger/", response_model=PassengerOut, status_code=status.HTTP_201_CREATED)
def create_passenger(
    passenger_data: PassengerIn,
    request: Request,
    db: Session = Depends(get_session)
):
    return AccidentService.create_passenger(request, passenger_data, db)
@accident_router.get("/passenger/{claim_id}", response_model=list[PassengerOut])
def get_passengers_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return AccidentService.get_passengers_by_claim_id(claim_id, db)

@accident_router.get("/passenger/by-id/{id}", response_model=PassengerOut)
def get_passenger_by_id(id: int, db: Session = Depends(get_session)):
    return AccidentService.get_passenger_by_id(id, db)

@accident_router.put("/update_passenger/{id}", response_model=PassengerOut)
def update_passenger(id: int, payload: PassengerIn, db: Session = Depends(get_session)):
    return AccidentService.update_passenger(id, payload, db)

@accident_router.patch("/deactive_passenger/{id}")
def deactivate_passenger(id: int, db: Session = Depends(get_session)):
    return AccidentService.deactivate_passenger(id, db)
#-----------Witness Detail----------------------
@accident_router.post("/witness/", response_model=WitnessOut, status_code=status.HTTP_201_CREATED)
def create_witness(
    witness_data: WitnessIn,
    request: Request,
    db: Session = Depends(get_session)
):
    return AccidentService.create_witness(request, witness_data, db)
@accident_router.get("/witness_detail/{claim_id}", response_model=list[WitnessOut])
def get_witness_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return AccidentService.get_witness_by_claim_id(claim_id, db)

@accident_router.get("/witness/{id}", response_model=WitnessOut)
def get_witness_by_id(id: int, db: Session = Depends(get_session)):
    return AccidentService.get_witness_by_id(id, db)

@accident_router.put("/update_witness/{id}", response_model=WitnessOut)
def update_witness_detail(id: int, payload: WitnessIn, db: Session = Depends(get_session)):
    return AccidentService.update_witness_detail(id, payload, db)

@accident_router.patch("/deactive_witness/{id}")
def deactivate_witness_detail(id: int, db: Session = Depends(get_session)):
    return AccidentService.deactivate_witness_detail(id, db)

#------------ Police Detail-------------
@accident_router.post("/police_detail/", response_model=PoliceDetailOut, status_code=status.HTTP_201_CREATED)
def create_police_detail(
    police_data: PoliceDetailIn,
    request: Request,
    db: Session = Depends(get_session)
):
    return AccidentService.create_police_detail(request, police_data, db)
@accident_router.get("/police_detail/{claim_id}", response_model=list[PoliceDetailOut])
def get_police_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return AccidentService.get_police_by_claim_id(claim_id, db)

@accident_router.get("/police_detail/by_id/{id}", response_model=PoliceDetailOut)
def get_police_by_id(id: int, db: Session = Depends(get_session)):
    return AccidentService.get_police_by_id(id, db)

@accident_router.put("/update_police/{id}", response_model=PoliceDetailOut)
def update_police_detail(id: int, payload: PoliceDetailIn, db: Session = Depends(get_session)):
    return AccidentService.update_police_detail(id, payload, db)

@accident_router.patch("/deactive_police/{id}")
def deactivate_police_detail(id: int, db: Session = Depends(get_session)):
    return AccidentService.deactivate_police_detail(id, db)