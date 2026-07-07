# appflow/routers/location_conditions.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError, EndpointConnectionError
import os
from libdata.settings import get_session
from appflow.utils import get_tenant_id,actor_id
from appflow.services.accident_service import AccidentService
from appflow.models.accident_detail import AccidentDetailIn, AccidentDetailOut

from appflow.models.passenger import PassengerOut, PassengerIn

from appflow.models.police_detail import PoliceDetailOut, PoliceDetailIn
from appflow.models.witness import WitnessOut, WitnessIn

accident_router = APIRouter(prefix="/accident-details", tags=["accidents"])

def get_latest_witness_questionnaire_from_s3(
    claim_id: int,
    witness_id: int | None = None,
):
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME", "crm-nationwide-assist")
    region_name = os.getenv("AWS_REGION", "eu-north-1")

    s3_client = boto3.client(
        "s3",
        region_name=region_name,
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=15,
            retries={"max_attempts": 2},
        ),
    )

    # This matches your upload path:
    # claims/11/documents/witness-questionnaires/xxx_Witness-Questionnaire.pdf
    prefix = f"claims/{claim_id}/documents/witness-questionnaires/"

    latest_file = None

    try:
        paginator = s3_client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key", "")

                if not key.lower().endswith(".pdf"):
                    continue

                if "witness" not in key.lower() and "questionnaire" not in key.lower():
                    continue

                if latest_file is None or item["LastModified"] > latest_file["LastModified"]:
                    latest_file = item

        if not latest_file:
            return None

        file_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket_name,
                "Key": latest_file["Key"],
            },
            ExpiresIn=3600,
        )

        return {
            "file_name": latest_file["Key"].split("/")[-1],
            "s3_key": latest_file["Key"],
            "file_url": file_url,
            "last_modified": latest_file["LastModified"].isoformat(),
        }

    except EndpointConnectionError as exc:
        print(f"[Witness Questionnaire] S3 endpoint/DNS error: {exc}")
        return None

    except (ClientError, BotoCoreError) as exc:
        print(f"[Witness Questionnaire] S3 error: {exc}")
        return None

    except Exception as exc:
        print(f"[Witness Questionnaire] Unexpected error: {exc}")
        return None

@accident_router.get("/witness/{witness_id}/latest-questionnaire")
def get_latest_witness_questionnaire(
    witness_id: int,
    db: Session = Depends(get_session),
):
    witness = AccidentService.get_witness_by_id(witness_id, db)

    if not witness:
        raise HTTPException(status_code=404, detail="Witness not found")

    latest_pdf = get_latest_witness_questionnaire_from_s3(
        claim_id=witness.claim_id,
        witness_id=witness.id,
    )

    if not latest_pdf:
        return {
            "status": "sent",
            "received": False,
            "file_url": None,
            "file_name": None,
            "s3_key": None,
            "message": "Questionnaire PDF is not available yet",
        }

    return {
        "status": "received",
        "received": True,
        "file_url": latest_pdf["file_url"],
        "file_name": latest_pdf["file_name"],
        "s3_key": latest_pdf["s3_key"],
        "last_modified": latest_pdf["last_modified"],
    }

@accident_router.post("/", response_model=AccidentDetailOut, status_code=status.HTTP_201_CREATED)
def create_accident_location(
    request: Request,
    accident_data: AccidentDetailIn,
    db: Session = Depends(get_session)
):
    tenant_id = get_tenant_id(request)
    current_user_id = actor_id(request)
    return AccidentService.create_location_condition(db, accident_data, tenant_id,current_user_id)

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
    claim_id: int,request: Request,
    data: AccidentDetailIn,
    db: Session = Depends(get_session)
):
    tenant_id = get_tenant_id(request)
    actor = actor_id(request)
    return AccidentService.update_location_condition(db, claim_id, data, tenant_id, actor)

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

@accident_router.put("/update-passenger/{id}", response_model=PassengerOut)
def update_passenger(id: int, payload: PassengerIn, db: Session = Depends(get_session),current_user=Depends(actor_id),tenant_id = Depends(get_tenant_id)):
    return AccidentService.update_passenger(id, payload, db,current_user,tenant_id)

@accident_router.patch("/deactive-passenger/{id}")
def deactivate_passenger(id: int, db: Session = Depends(get_session),actor_id = Depends(actor_id)):
    return AccidentService.deactivate_passenger(id, db,actor_id)
#-----------Witness Detail----------------------
@accident_router.post("/witness/", response_model=WitnessOut, status_code=status.HTTP_201_CREATED)
def create_witness(
    witness_data: WitnessIn,
    request: Request,
    db: Session = Depends(get_session)
):
    return AccidentService.create_witness(request, witness_data, db)
@accident_router.get("/witness-detail/{claim_id}", response_model=list[WitnessOut])
def get_witness_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return AccidentService.get_witness_by_claim_id(claim_id, db)

@accident_router.get("/witness/{id}", response_model=WitnessOut)
def get_witness_by_id(id: int, db: Session = Depends(get_session)):
    return AccidentService.get_witness_by_id(id, db)

@accident_router.put("/update-witness/{id}", response_model=WitnessOut)
def update_witness_detail(id: int, payload: WitnessIn,request: Request, db: Session = Depends(get_session)):
    tenant_id = get_tenant_id(request)
    current_user = actor_id(request)
    return AccidentService.update_witness_detail(id, payload, db, tenant_id, current_user)

@accident_router.patch("/deactive-witness/{id}")
def deactivate_witness_detail(id: int,request: Request, db: Session = Depends(get_session)):
    tenant_id = get_tenant_id(request)
    current_user = actor_id(request)
    return AccidentService.deactivate_witness_detail(id, db,tenant_id,current_user)

#------------ Police Detail-------------
@accident_router.post("/police-detail/", response_model=PoliceDetailOut, status_code=status.HTTP_201_CREATED)
def create_police_detail(
    police_data: PoliceDetailIn,
    request: Request,
    db: Session = Depends(get_session)
):
    return AccidentService.create_police_detail(request, police_data, db)
@accident_router.get("/police-detail/{claim_id}", response_model=list[PoliceDetailOut])
def get_police_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return AccidentService.get_police_by_claim_id(claim_id, db)

@accident_router.get("/police-detail/by_id/{id}", response_model=PoliceDetailOut)
def get_police_by_id(id: int, db: Session = Depends(get_session)):
    return AccidentService.get_police_by_id(id, db)

@accident_router.put("/update-police/{id}", response_model=PoliceDetailOut)
def update_police_detail(id: int,request: Request, payload: PoliceDetailIn, db: Session = Depends(get_session)):
    return AccidentService.update_police_detail(id, payload, db, request)

@accident_router.patch("/deactive-police/{id}")
def deactivate_police_detail(id: int,request: Request, db: Session = Depends(get_session)):
    return AccidentService.deactivate_police_detail(id, db,request)