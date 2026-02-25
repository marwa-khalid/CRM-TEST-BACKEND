# app/schemas/claims.py
from typing import Optional, Literal, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator

Tri = Literal["YES", "NO", "TBC"]

class ClaimBase(BaseModel):
    # Lookup FKs (all optional; service enforces rules)
    claim_type_id: Optional[int] = None
    handler_id: Optional[int] = None
    target_debt_id: Optional[int] = None
    case_status_id: Optional[int] = None

    source_id: Optional[int] = None
    source_staff_user_id: Optional[int] = None
    prospects_id: Optional[int] = None
    present_position_id: Optional[int] = None

    credit_hire_accepted: Optional[bool] = None
    non_fault_accident: Optional[Tri] = None
    any_passengers: Optional[Tri] = None
    client_injured: Optional[Tri] = None

    client_going_abroad: Optional[bool] = False
    abroad_date: Optional[date] = None

    @field_validator("non_fault_accident", "any_passengers", "client_injured")
    @classmethod
    def _normalize_tri(cls, v):
        return v if v is None else v.upper()

class ClaimCreate(ClaimBase):
    pass

class ClaimUpdate(ClaimBase):
    pass

class ClaimOut(ClaimBase):
    id: int
    file_opened_at: Optional[datetime]=None
    file_closed_at: Optional[datetime] = None
    file_closed_reason: Optional[str] = None
    is_locked: bool = False
    manager_notified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Convenience display labels for UI
    labels: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class CloseClaimRequest(BaseModel):
    reason: str = Field(..., min_length=2)

class NotifyManagerRequest(BaseModel):
    note: Optional[str] = None
