import time
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from appflow.models.authentication import RegisterRequest
from libdata.models.tables import User, Tenant
from libauth.token_util import verify_hash, sign_jwt, create_hash
from appflow.logger import logger
from appflow.models.authentication import LoginRequest
from libauth.token_util import decode_auth_token


from pydantic import BaseModel

class ResetPasswordRequest(BaseModel):
    email: str
    password: str

def register_user(user_name: str, db: Session):
    try:
        email = user_name.lower().strip()

        # Check if user already exists
        existing_user = db.query(User).filter(User.user_name == email).first()
        if existing_user:
            return {
                "success": False,
                "status": 400,
                "message": "User already exists."
            }

        # Create Tenant (UUID auto-generated)
        tenant_obj = Tenant(
            name=email.split("@")[0]
        )

        db.add(tenant_obj)
        db.flush()  # ensures tenant_obj.id is generated

        # Create User with empty password
        new_user = User(
            user_name=email,
            password=None,
            first_name=None,
            last_name=None,
            tenant_id=tenant_obj.id
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "success": True,
            "status": 200,
            "message": "User created successfully. Please set your password.",
            "tenant_id": tenant_obj.id
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "status": 500,
            "message": str(e)
        }

def reset_password(user_name: str, password: str, db: Session):
    try:
        user = db.query(User).filter(User.user_name == user_name).first()

        if not user:
            return {"success": False, "status": 404, "message": "User not found"}

        hashed_password = create_hash(password)
        user.password = hashed_password

        db.commit()

        return {
            "success": True,
            "status": 200,
            "message": "Password updated successfully"
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "status": 500, "message": str(e)}

def verify_user(payload: LoginRequest, db: Session):
    try:
        user: User = db.query(User).filter(User.user_name == payload.user_name).one()
        if not user or not verify_hash(payload.password, user.password):
            return None

        # Generate JWT token
        token = sign_jwt({"sub": user.user_name, "user_id": user.id, "tenant_id": user.tenant_id})
        issue_time = datetime.utcnow()
        expiry_time = issue_time + timedelta(days=365)  # One year expiry time
        user_data = {
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.user_name,
            "is_active":user.is_active,
            "iat": int(time.mktime(issue_time.timetuple())),  # Issue time
            "exp": int(time.mktime(expiry_time.timetuple())),  # Expiry time
            "first_name": user.first_name,
            "last_name" : user.last_name,
        }
        # Assemble user data

        # Return token and user data like the old project
        return { **token,**user_data}

    except NoResultFound:
        logger.warning(f"User not found: {payload.user_name}")
        return None



def generate_deep_link_token(user: User, claim_id: int) -> str:
    issue_time = datetime.utcnow()
    expiry_time = issue_time + timedelta(weeks=1)
    token_payload = {
        "sub": user.user_name,
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "iat": int(time.mktime(issue_time.timetuple())),  # Issue time
        "exp": int(time.mktime(expiry_time.timetuple())),  # Expiry time
        "type": "deep_link" , # Token type for deep link
        claim_id: claim_id
    }
    return sign_jwt(token_payload)

def save_questionnaire(auth_token: str, db: Session):
    # Decode the token
    decoded_link = decode_auth_token(auth_token)

    # Extract claim_id and user_id from the decoded token
    claim_id = decoded_link.get('claim_id')
    user_id = decoded_link.get('user_id')

    # Validate token expiry
    if datetime.utcfromtimestamp(decoded_link['exp']) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token has expired")