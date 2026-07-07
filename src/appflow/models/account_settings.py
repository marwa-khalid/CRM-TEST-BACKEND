from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class RegisterSessionRequest(BaseModel):
    ip_address: Optional[str] = None
    device_info: Optional[str] = None


class SessionOut(BaseModel):
    id: int
    ip_address: Optional[str] = None
    device_info: Optional[str] = None
    is_current: Optional[bool] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
