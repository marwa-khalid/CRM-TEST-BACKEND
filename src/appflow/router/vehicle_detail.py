from fastapi import APIRouter, Depends,UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
from libdata.settings import get_session
from appflow.models.vehicle_detail import (
    ClientVehicleCreate, ClientVehicleResponse
)
from appflow.services.vehicle_detail import ( create_client_vehicle,get_client_vehicle,list_client_vehicles,
update_client_vehicle,delete_client_vehicle,
                                              )
from fastapi.responses import JSONResponse
from appflow.services.ocr_Service import ocr_service
from appflow.services.vehicle_upload_service import process_client_vehicle


vehicle_router = APIRouter(prefix="/client-vehicles", tags=["Client Vehicles"])


@vehicle_router.post("/", response_model=ClientVehicleResponse)
def create_client_vehicle_router(vehicle: ClientVehicleCreate, db: Session = Depends(get_session)):
    return create_client_vehicle(vehicle, db)


@vehicle_router.get("/{claim_id}", response_model=ClientVehicleResponse)
def get_client_vehicle_router(claim_id: int, db: Session = Depends(get_session)):
    return get_client_vehicle(claim_id, db)


@vehicle_router.get("/claim/{claim_id}", response_model=List[ClientVehicleResponse])
def list_client_vehicles_router(claim_id: int, db: Session = Depends(get_session)):
    return list_client_vehicles(claim_id, db)


@vehicle_router.put("/{claim_id}", response_model=ClientVehicleResponse)
def update_client_vehicle_router(claim_id: int, vehicle: ClientVehicleCreate, db: Session = Depends(get_session)):
    return update_client_vehicle(claim_id, vehicle, db)


@vehicle_router.delete("/{vehicle_id}")
def delete_client_vehicle_router(vehicle_id: int, db: Session = Depends(get_session)):
    return delete_client_vehicle(vehicle_id, db)

@vehicle_router.post("/import_client_vehicle/")
async def import_client_vehicle(files: list[UploadFile] = File(...), db: Session = Depends(get_session)):
    # Call import_client_vehicle function, passing only the required arguments
    vehicle_details = process_client_vehicle(files, db, ocr_service)

    return JSONResponse(content={"client_vehicle_detail": vehicle_details}, status_code=200)