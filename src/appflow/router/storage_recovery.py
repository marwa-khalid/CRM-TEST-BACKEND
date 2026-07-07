from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from libdata.settings import get_session
from appflow.utils import get_tenant_id,actor_id
from appflow.models.storage_recovery import (
    StorageRecoveryIn,
    StorageRecoveryOut,StorageOut,RecoveryOut,StorageRecoveryUpdateOut,StorageRecoveryUpdateIn
)
from appflow.services.storage_recovery_service import StorageRecoveryService
from libdata.models.tables import Address,Storage,Recovery

storage_recovery_router = APIRouter(
    prefix="/storage-recovery", tags=["Storage & Recovery"]
)


@storage_recovery_router.post("/", response_model=StorageRecoveryOut)
def create_storage_recovery(
    data: StorageRecoveryIn,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(actor_id)
):
    return StorageRecoveryService.create_storage_recovery(
        payload=data,
        db=db,
        tenant_id=tenant_id,
        user_id=user_id
    )


@storage_recovery_router.get("/{claim_id}", response_model=StorageRecoveryOut)
def get_storage_recovery_by_claim(
    claim_id: int,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    return StorageRecoveryService.get_storage_recovery_by_claim(
        claim_id, db, tenant_id
    )

@storage_recovery_router.put("/{claim_id}", response_model=StorageRecoveryOut)
def update_storage_recovery_by_claim(
    claim_id: int,
    payload: StorageRecoveryUpdateIn,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
    current_user_id: int = Depends(actor_id)
):
    """
    Update all Storage and Recovery records for a claim_id.
    Each record in the payload will be matched to the existing DB record by index/order.
    """
    return StorageRecoveryService.update_storage_recovery_by_claim(
        claim_id, payload, db, tenant_id, current_user_id
    )

@storage_recovery_router.get("/search-storage/{query}", response_model=List[StorageOut])
def search_storage_route(
    query: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return StorageRecoveryService.search_storage(query, db, tenant_id)


@storage_recovery_router.get("/search-recovery/{query}", response_model=List[RecoveryOut])
def search_recovery_route(
    query: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id)
):
    return StorageRecoveryService.search_recovery(query, db, tenant_id)