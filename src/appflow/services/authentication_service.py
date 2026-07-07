import time
from datetime import datetime, timedelta
import random
import os
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from appflow.logger import logger
from appflow.models.authentication import LoginRequest
from appflow.services.invite_service import send_invite_email, send_otp_email
from libauth.token_util import verify_hash, sign_jwt, create_hash, decode_auth_token
from libdata.models.tables import User, Tenant

class ResetPasswordRequest(BaseModel):
    email: str
    password: str

OTP_STORE = {}
OTP_EXPIRY_SECONDS = 300
RETURN_OTP_IN_RESPONSE = os.getenv("RETURN_OTP_IN_RESPONSE", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def invite_user(user_name: str, db: Session):
    try:
        email = user_name.lower().strip()

        existing_user = db.query(User).filter(User.user_name == email).first()

        # Fully registered user already exists
        if existing_user and existing_user.password:
            return {
                "success": False,
                "status": 400,
                "message": "User already exists."
            }

        # Invited but not completed yet -> resend invite email
        if existing_user and not existing_user.password:
            send_invite_email(email)
            return {
                "success": True,
                "status": 200,
                "message": "Invitation resent successfully.",
                "tenant_id": existing_user.tenant_id
            }

        # Single-company: all users share the same tenant.
        # Use the existing tenant, or create one if the DB is empty.
        tenant_obj = db.query(Tenant).first()
        if not tenant_obj:
            tenant_obj = Tenant(name="Default")
            db.add(tenant_obj)
            db.flush()

        new_user = User(
            user_name=email,
            password=None,
            first_name=None,
            last_name=None,
            tenant_id=tenant_obj.id,
            is_active=False if hasattr(User, "is_active") else None,
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # send email AFTER commit
        send_invite_email(email)

        return {
            "success": True,
            "status": 200,
            "message": "Invitation sent successfully.",
            "tenant_id": tenant_obj.id
        }

    except Exception as e:
        db.rollback()
        logger.exception("Invite user failed")
        return {
            "success": False,
            "status": 500,
            "message": str(e)
        }


def reset_password(user_name: str, password: str, db: Session):
    try:
        email = user_name.lower().strip()

        user = db.query(User).filter(User.user_name == email).first()

        if not user:
            return {
                "success": False,
                "status": 404,
                "message": "User not found"
            }

        if not password or len(password) < 8:
            return {
                "success": False,
                "status": 400,
                "message": "Password must be at least 8 characters long"
            }

        hashed_password = create_hash(password)
        user.password = hashed_password

        if hasattr(user, "is_active"):
            user.is_active = True

        db.commit()

        return {
            "success": True,
            "status": 200,
            "message": "Password updated successfully. Invitation completed."
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "status": 500,
            "message": str(e)
        }


# Server-side brute-force lockout policy.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _account_locked_error(retry_after_seconds: int):
    """423 Locked — the frontend routes to /account-locked on this status."""
    return HTTPException(
        status_code=423,
        detail={
            "message": "Account temporarily locked due to multiple unsuccessful login attempts.",
            "retry_after_seconds": max(0, int(retry_after_seconds)),
        },
    )


def verify_user(payload: LoginRequest, db: Session):
    try:
        email = payload.user_name.lower().strip()
        user: User = db.query(User).filter(User.user_name == email).first()
        if not user:
            # Don't reveal whether the account exists.
            return None

        now = datetime.utcnow()

        # Already locked? Reject without even checking the password.
        if user.locked_until and user.locked_until.replace(tzinfo=None) > now:
            raise _account_locked_error((user.locked_until.replace(tzinfo=None) - now).total_seconds())

        # Wrong credentials → count the failure and lock at the threshold.
        if not user.password or not verify_hash(payload.password, user.password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                db.commit()
                raise _account_locked_error(LOCKOUT_MINUTES * 60)
            db.commit()
            return None

        # Success → clear any failure/lock state.
        if user.failed_login_attempts or user.locked_until:
            user.failed_login_attempts = 0
            user.locked_until = None
            db.commit()

        token = sign_jwt({
            "sub": user.user_name,
            "user_id": user.id,
            "tenant_id": user.tenant_id
        })

        issue_time = datetime.utcnow()
        expiry_time = issue_time + timedelta(days=365)

        user_data = {
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.user_name,
            "is_active": getattr(user, "is_active", None),
            "iat": int(time.mktime(issue_time.timetuple())),
            "exp": int(time.mktime(expiry_time.timetuple())),
            "first_name": user.first_name,
            "last_name": user.last_name,
        }

        return {**token, **user_data}

    except NoResultFound:
        logger.warning(f"User not found: {payload.user_name}")
        return None

def send_login_otp(user_name: str, db: Session):
    try:
        email = user_name.lower().strip()

        user = db.query(User).filter(User.user_name == email).first()
        if not user:
            return {
                "success": False,
                "status": 404,
                "message": "User not found"
            }

        otp = str(random.randint(100000, 999999))

        OTP_STORE[email] = {
            "otp": otp,
            "expires_at": time.time() + OTP_EXPIRY_SECONDS
        }

        first_name = user.first_name or ""
        send_otp_email(email, otp, first_name)

        response = {
            "success": True,
            "status": 200,
            "message": "OTP sent successfully"
        }
        if RETURN_OTP_IN_RESPONSE:
            response["otp"] = otp
        return response

    except Exception as e:
        logger.exception("Send OTP failed")
        return {
            "success": False,
            "status": 500,
            "message": str(e)
        }


def verify_login_otp(user_name: str, otp: str):
    try:
        email = user_name.lower().strip()
        otp_record = OTP_STORE.get(email)

        if not otp_record:
            return {
                "success": False,
                "status": 400,
                "message": "OTP not found"
            }

        if time.time() > otp_record["expires_at"]:
            del OTP_STORE[email]
            return {
                "success": False,
                "status": 400,
                "message": "OTP expired"
            }

        if otp_record["otp"] != otp:
            return {
                "success": False,
                "status": 400,
                "message": "Invalid OTP"
            }

        del OTP_STORE[email]

        return {
            "success": True,
            "status": 200,
            "message": "OTP verified successfully"
        }

    except Exception as e:
        logger.exception("Verify OTP failed")
        return {
            "success": False,
            "status": 500,
            "message": str(e)
        }


def forgot_password(user_name: str, db: Session):
    try:
        email = user_name.lower().strip()
        user = db.query(User).filter(User.user_name == email).first()
        if not user or not user.password:
            # Don't reveal whether the account exists
            return {"success": True, "status": 200, "message": "If an account exists, a reset link has been sent."}
        send_invite_email(email)
        return {"success": True, "status": 200, "message": "Password reset email sent successfully."}
    except Exception as e:
        logger.exception("Forgot password failed")
        return {"success": False, "status": 500, "message": str(e)}


def generate_deep_link_token(user: User, claim_id: int) -> str:
    issue_time = datetime.utcnow()
    expiry_time = issue_time + timedelta(weeks=1)

    token_payload = {
        "sub": user.user_name,
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "iat": int(time.mktime(issue_time.timetuple())),
        "exp": int(time.mktime(expiry_time.timetuple())),
        "type": "deep_link",
        "claim_id": claim_id,
    }

    return sign_jwt(token_payload)

def save_questionnaire(auth_token: str, db: Session):
    decoded_link = decode_auth_token(auth_token)

    claim_id = decoded_link.get("claim_id")
    user_id = decoded_link.get("user_id")

    if datetime.utcfromtimestamp(decoded_link["exp"]) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token has expired")

    return {
        "success": True,
        "status": 200,
        "message": "Questionnaire token verified",
        "claim_id": claim_id,
        "user_id": user_id,
    }
