from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from libdata.settings import get_session
from appflow.models.hire_record import HireRecordsIn, HireRecordOut
from appflow.services.hire_record_service import HireRecordService
from appflow.utils import actor_id

hire_record_router = APIRouter(prefix="/hire-records", tags=["Hire Records"])


@hire_record_router.get("/{claim_id}", response_model=List[HireRecordOut])
def get_hire_records(
    claim_id: int,
    db: Session = Depends(get_session),
):
    return HireRecordService.get_by_claim(claim_id, db)


@hire_record_router.post("/", response_model=List[HireRecordOut])
def save_hire_records(
    payload: HireRecordsIn,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
):
    return HireRecordService.save(payload, db, current_user)
