# appflow/models/authentication.py
from pydantic import BaseModel,EmailStr

# class RegisterRequest(BaseModel):
#     user_name: str
#     password: str
#     first_name: str
#     last_name:str
#     company_name: str
class RegisterRequest(BaseModel):
    user_name: EmailStr


class LoginRequest(BaseModel):
    user_name: str
    password: str
