from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from appflow.utils import get_tenant_id
from libdata.models.tables import ClientDetail, Address
from appflow.models.client_detail import ClientDetailIn
from libdata.enums import PersonRoleEnum


def create_client_service(request: Request, client: ClientDetailIn, db: Session, role: PersonRoleEnum):
    tenant_id = get_tenant_id(request)
    print(tenant_id)
    # Extra validation for CLIENT role
    if role == PersonRoleEnum.CLIENT:
        required_fields = {
            "date_of_birth": client.date_of_birth,
            "ni_number": client.ni_number,
            "sort_code": client.sort_code,
            "account_number": client.account_number,
            "surname": client.surname,
            "language": client.language_id,
        }
        # missing = [field for field, value in required_fields.items() if not value]
        # if missing:
        #     raise HTTPException(
        #         status_code=422,
        #         detail=f"Missing required fields for CLIENT role: {', '.join(missing)}"
        #     )

    # 1. Save Address if provided
    address_id = None
    if client.address:
        db_address = Address(**client.address.dict())
        db.add(db_address)
        db.flush()
        db.refresh(db_address)
        address_id = db_address.id

    # 2. Save ClientDetail
    db_client = ClientDetail(
        **client.dict(exclude={"address", "tenant_id"}),
        tenant_id=tenant_id,
        address_id=address_id,
        role=role.value if isinstance(role, PersonRoleEnum) else role,
    )

    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    return db_client

def list_clients_service(request: Request, db: Session, role: PersonRoleEnum | None = None):
    tenant_id = get_tenant_id(request)

    query = db.query(ClientDetail).filter(ClientDetail.tenant_id == tenant_id)

    if role:
        query = query.filter(ClientDetail.role == role)

    return query.all()


def get_client_service(client_id: int, request: Request, db: Session, role: PersonRoleEnum | None = None):
    tenant_id = get_tenant_id(request)

    query = db.query(ClientDetail).filter(ClientDetail.id == client_id, ClientDetail.tenant_id == tenant_id)

    if role:
        query = query.filter(ClientDetail.role == role)

    client = query.first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return client
def get_client_by_claim_id(claim_id: int, request: Request, db: Session, role: PersonRoleEnum | None = None):
    tenant_id = get_tenant_id(request)

    query = db.query(ClientDetail).filter(ClientDetail.claim_id == claim_id)

    if role:
        query = query.filter(ClientDetail.role == role)

    client = query.first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return client

def update_client_service(claim_id: int, request: Request, client_data: ClientDetailIn, db: Session, role: PersonRoleEnum):
    tenant_id = get_tenant_id(request)
    db_client = (
        db.query(ClientDetail)
        .filter(ClientDetail.claim_id == claim_id)
        .first()
    )

    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Update client fields (exclude nested address)
    for key, value in client_data.dict(exclude={"address"}).items():
        setattr(db_client, key, value)

    # Handle address update/create
    if client_data.address:
        if db_client.address:
            for key, value in client_data.address.dict().items():
                setattr(db_client.address, key, value)
        else:
            db_client.address = Address(**client_data.address.dict())

    db.commit()
    db.refresh(db_client)
    return db_client


def deactivate_client_service(claim_id: int, request: Request, db: Session, role: PersonRoleEnum | None = None):
    tenant_id = get_tenant_id(request)

    query = db.query(ClientDetail).filter(ClientDetail.claim_id == claim_id, ClientDetail.tenant_id == tenant_id)

    if role:
        query = query.filter(ClientDetail.role == role)

    db_client = query.first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")

    db_client.is_active = False
    db.commit()
    db.refresh(db_client)

    return {"detail": "Client deactivated successfully"}