from pydantic import BaseModel, EmailStr
from typing import Optional


class EmailCTARequest(BaseModel):
    to_email: Optional[str] = None