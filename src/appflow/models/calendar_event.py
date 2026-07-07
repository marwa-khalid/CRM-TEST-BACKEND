from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


class CalendarEventIn(BaseModel):
    title: str
    event_type: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    start_time: Optional[str] = None
    end_date: Optional[date] = None
    end_time: Optional[str] = None
    assigned_users: Optional[List[str]] = None
    department: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    reminder: Optional[str] = None
    recurrence_rule: Optional[str] = None
    attachment_path: Optional[str] = None
    attachment_name: Optional[str] = None
    claim_id: Optional[int] = None
    claim_reference: Optional[str] = None
    case_reference: Optional[str] = None
    task_id: Optional[int] = None
    vehicle_registration: Optional[str] = None


class CalendarEventOut(BaseModel):
    id: int
    title: str
    event_type: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    start_time: Optional[str] = None
    end_date: Optional[date] = None
    end_time: Optional[str] = None
    assigned_users: List[str] = []
    department: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    reminder: Optional[str] = None
    recurrence_rule: Optional[str] = None
    attachment_path: Optional[str] = None
    attachment_name: Optional[str] = None
    claim_id: Optional[int] = None
    claim_reference: Optional[str] = None
    case_reference: Optional[str] = None
    task_id: Optional[int] = None
    vehicle_registration: Optional[str] = None
    source: Optional[str] = None
    source_type: Optional[str] = None
    source_ref_id: Optional[int] = None
    reminder_sent: Optional[bool] = None
    recurrence_rule: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # True for a generated occurrence of a recurring series (shares the base id).
    is_occurrence: bool = False
    # Linked-record context for the Event Details drawer
    claimant_name: Optional[str] = None
    case_status: Optional[str] = None

    class Config:
        from_attributes = True
