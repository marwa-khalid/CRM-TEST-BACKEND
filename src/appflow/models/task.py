from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_user: Optional[str] = None
    department: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[str] = None
    priority: Optional[str] = "Medium"
    status: Optional[str] = "Pending"
    claim_id: Optional[int] = None
    claim_reference: Optional[str] = None
    vehicle_registration: Optional[str] = None
    attachment_path: Optional[str] = None
    notes: Optional[str] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_user: Optional[str] = None
    department: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    claim_id: Optional[int] = None
    claim_reference: Optional[str] = None
    vehicle_registration: Optional[str] = None
    attachment_path: Optional[str] = None
    notes: Optional[str] = None


class ReassignRequest(BaseModel):
    new_assignee: str
    reason: Optional[str] = None
    notify_new: bool = True
    notify_previous: bool = False


class NoteCreate(BaseModel):
    text: str


class TaskOut(TaskBase):
    id: int
    is_overdue: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskListOut(BaseModel):
    items: List[TaskOut]
    total: int
    page: int
    page_size: int


class TaskStatsOut(BaseModel):
    total: int
    pending: int
    in_progress: int
    overdue: int
    completed: int
