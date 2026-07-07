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

    # Reason shown when the case status is "Rejected".
    rejection_reason: Optional[str] = None

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

class ClaimListOut(BaseModel):
    claim_id: int
    our_reference : str
    client_name : Optional[str]
    mobile_tel: Optional[str]
    incident_date: Optional[datetime]
    actual_category: Optional[str]
    claim_type: Optional[str] = None
    handler: Optional[str]
    case_status: Optional[str]
    rejection_reason: Optional[str] = None
    latest_update_str: Optional[str]
    priority:str
    file_opened_at: datetime

    class Config:
        from_attributes = True

class ClaimDisplayLabels:
    labels = {
        "claim_type_id": "Claim type",
        "handler_id": "Handler",
        "target_debt_id": "Target debt",
        "case_status_id": "Case status",
        "source_id": "How did the customer find us?",
        "source_staff_user_id": "If staff marketing which?",
        "prospects_id": "Prospects of file",
        "present_position_id": "Present file position",
        "credit_hire_accepted": "Credit hire accepted?",
        "non_fault_accident": "Non-fault accident",
        "any_passengers": "Any passengers?",
        "client_injured": "Client injured?",
        "client_going_abroad": "Client going abroad soon?",
        "abroad_date": "Date",
        "rejection_reason": "Rejection reason",
    }

    @classmethod
    def format(cls, field_name: str):
        return cls.labels.get(field_name, field_name.replace("_", " ").title())