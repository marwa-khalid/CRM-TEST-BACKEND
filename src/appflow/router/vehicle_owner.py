# from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException,UploadFile,File
# from sqlalchemy.orm import Session
# from typing import List
# from libdata.settings import get_session
# from appflow.models.vehicle_owner import VehicleOwnerIn, VehicleOwnerOut
# from appflow.services.vehicle_owner_service import (
#     create_vehicle_owner_service,
#     list_vehicle_owner_service,
#     get_vehicle_owner_service,
#     update_vehicle_owner_service,
#     deactivate_vehicle_owner_service,
# )
# from appflow.services.import_job_service import import_job_service
# from appflow.services.import_utils import serialize_uploads
# from appflow.services.import_workers import run_vehicle_owner_import
# from libdata.enums import PersonRoleEnum
# from appflow.utils import actor_id,get_tenant_id

# vehicle_owner_router = APIRouter(prefix="/vehicle-owners", tags=["Vehicle Owners"])

# @vehicle_owner_router.post("/", response_model=VehicleOwnerOut)
# def create_vehicle_owner(
#     request: Request, owner: VehicleOwnerIn, db: Session = Depends(get_session)
# ):
#     return create_vehicle_owner_service(request, owner, db, role=PersonRoleEnum.VEHICLE_OWNER)


# @vehicle_owner_router.get("/", response_model=List[VehicleOwnerOut])
# def list_vehicle_owners(request: Request, db: Session = Depends(get_session)):
#     return list_vehicle_owner_service(request, db, role=PersonRoleEnum.VEHICLE_OWNER)


# @vehicle_owner_router.get("/{claim_id}", response_model=VehicleOwnerOut)
# def get_vehicle_owner(claim_id: int, request: Request, db: Session = Depends(get_session)):
#     return get_vehicle_owner_service(claim_id, request, db, role=PersonRoleEnum.VEHICLE_OWNER)


# @vehicle_owner_router.put("/{claim_id}", response_model=VehicleOwnerOut)
# def update_vehicle_owner(
#     claim_id: int,
#     request: Request,
#     owner_data: VehicleOwnerIn,
#     db: Session = Depends(get_session)
# ):
#     return update_vehicle_owner_service(claim_id, request, owner_data, db, role=PersonRoleEnum.VEHICLE_OWNER)


# @vehicle_owner_router.delete("/{claim_id}")
# def deactivate_vehicle_owner(claim_id: int, request: Request, db: Session = Depends(get_session)):
#     return deactivate_vehicle_owner_service(claim_id, request, db, role=PersonRoleEnum.VEHICLE_OWNER)

# @vehicle_owner_router.post("/import-vehicle-owner/", status_code=202)
# async def import_vehicle_owner(
#     claim_id: int,
#     request:Request,
#     background_tasks: BackgroundTasks,
#     files: list[UploadFile] = File(...),
# ):
#     actor = actor_id(request)
#     tenant_id = get_tenant_id(request)
#     payloads = await serialize_uploads(files)
#     job = import_job_service.create_job("vehicle_owner_import")
#     background_tasks.add_task(run_vehicle_owner_import, job.id, payloads, claim_id, actor,tenant_id)
#     return {"job_id": job.id, "status": job.status.value}