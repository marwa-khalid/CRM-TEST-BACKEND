# appflow/models/authentication.py

from pydantic import BaseModel, EmailStr
from typing import Optional


class LoginRequest(BaseModel):
    user_name: EmailStr
    password: str


class RegisterRequest(BaseModel):
    user_name: EmailStr


class InviteUserRequest(BaseModel):
    user_name: EmailStr

class SendOtpRequest(BaseModel):
    user_name: EmailStr

class VerifyOtpRequest(BaseModel):
    user_name: EmailStr
    otp: str