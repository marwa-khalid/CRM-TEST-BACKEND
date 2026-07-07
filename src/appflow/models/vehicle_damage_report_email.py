from pydantic import BaseModel, EmailStr
from typing import Optional


class DamageReportEmailRequest(BaseModel):
    recipient_email: Optional[EmailStr] = None  # Will be fetched from DB if not provided
    recipient_name: Optional[str] = "Recipient"
    message: Optional[str] = None
    # No longer need vehicle IDs - will fetch all vehicles for the claim automatically


class DamageReportEmailResponse(BaseModel):
    status: str
    message: str
    report_id: Optional[str] = None
