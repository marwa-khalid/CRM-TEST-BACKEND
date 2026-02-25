from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from libdata.settings import get_session
from appflow.models.client_detail import ClientDetailIn, ClientDetailOut
from appflow.services.client_service import (
    create_client_service,
    list_clients_service,
    get_client_service,
    update_client_service,
    deactivate_client_service,
)

from appflow.services.client_service import get_client_by_claim_id
from libdata.enums import PersonRoleEnum

client_router = APIRouter(prefix="/clients", tags=["Clients"])


@client_router.post("/", response_model=ClientDetailOut)
def create_client(
    request: Request, client: ClientDetailIn, db: Session = Depends(get_session)
):
    return create_client_service(request, client, db, role=PersonRoleEnum.CLIENT)


@client_router.get("/", response_model=List[ClientDetailOut])
def list_clients(request: Request, db: Session = Depends(get_session)):
    return list_clients_service(request, db, role=PersonRoleEnum.CLIENT)


@client_router.get("/{client_id}", response_model=ClientDetailOut)
def get_client(client_id: int, request: Request, db: Session = Depends(get_session)):
    return get_client_service(client_id, request, db, role=PersonRoleEnum.CLIENT)


@client_router.get("/claim/{claim_id}", response_model=ClientDetailOut)
def get_client_by_claim(claim_id: int, request: Request, db: Session = Depends(get_session)):
    return get_client_by_claim_id(claim_id, request, db, role=PersonRoleEnum.CLIENT)


@client_router.put("/{claim_id}", response_model=ClientDetailOut)
def update_client(
    claim_id: int,
    request: Request,
    client_data: ClientDetailIn,
    db: Session = Depends(get_session)
):
    return update_client_service(claim_id, request, client_data, db, role=PersonRoleEnum.CLIENT)


@client_router.delete("/{claim_id}")
def deactivate_client(claim_id: int, request: Request, db: Session = Depends(get_session)):
    return deactivate_client_service(claim_id, request, db, role=PersonRoleEnum.CLIENT)