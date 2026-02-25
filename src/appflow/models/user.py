# appflow/models/user.py
from pydantic import BaseModel

class UserResponse(BaseModel):
    id: int
    user_name: str
    first_name: str
    last_name: str
    tenant_id: int

    class Config:
        orm_mode = True
