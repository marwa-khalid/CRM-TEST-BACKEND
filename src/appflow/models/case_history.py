from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# The 6 supported Case History actions (wire values match CaseHistoryActionType).
CASE_HISTORY_ACTIONS = [
    "send_letter",
    "send_email",
    "incoming_call",
    "outgoing_call",
    "note",
    "diary",
]


class CaseHistoryCreate(BaseModel):
    action_type: str  # one of CASE_HISTORY_ACTIONS
    correspondent: Optional[str] = None
    handler: Optional[str] = None
    subject: Optional[str] = None
    details: Optional[str] = None
    # Type-specific fields (email to/cc/bcc/body, letter template, call phrase/number,
    # note tag, diary action/assignee/due). Free-form so each activity form can grow.
    payload: Optional[Dict[str, Any]] = None
    # Optional explicit post time; defaults to now server-side when omitted.
    posted_at: Optional[datetime] = None


class CaseHistoryOut(BaseModel):
    id: int
    claim_id: Optional[int] = None   # None for fleet (hire / VM vehicle) records
    scope_type: Optional[str] = None  # 'claim' | 'fleet_hire' | 'vm_cams' | 'vm_skyline'
    scope_id: Optional[int] = None
    action_type: Optional[str] = None
    posted_at: Optional[datetime] = None
    correspondent: Optional[str] = None
    handler: Optional[str] = None
    subject: Optional[str] = None
    details: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


class CaseHistoryCorrespondent(BaseModel):
    """A third-party email address on the claim, for the Correspondent dropdown."""
    role: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class CaseHistoryFilterOptions(BaseModel):
    """Distinct values present in a claim's history, for the filter dropdowns."""
    correspondents: List[str] = []
    handlers: List[str] = []
    action_types: List[str] = []
