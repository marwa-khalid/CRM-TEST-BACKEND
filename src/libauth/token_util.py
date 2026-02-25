# libauth/token_util.py
from typing import Dict, Optional
import bcrypt
import jwt
from appflow.logger import logger


secret = 'zucyqIFhk9-D4B_LvwXkegs6kEytoqFOyL_aeCOl48YE'
algorithm = 'HS256'

def create_hash(plain_text: str):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(str.encode(plain_text), salt)
    return str(hashed, "UTF-8")

def verify_hash(plain_text: str, hashed_text: str):
    return bcrypt.checkpw(str.encode(plain_text), str.encode(hashed_text))

def sign_jwt(payload: dict) -> Dict[str, str]:
    token = jwt.encode(payload, secret, algorithm=algorithm)
    return {"access_token": token, "token_type": "bearer"}

def decode_jwt(token: str) -> dict:
    try:
        decoded_token = jwt.decode(token, secret, algorithms=[algorithm])
        logger.debug(f"decoded_token: {decoded_token}")
        return decoded_token
    except jwt.DecodeError:
        return {}

def decode_auth_token(auth_token: str) -> Optional[dict]:
    if not auth_token:
        logger.error("No authentication token provided.")
        return {}
    try:
        auth_token = auth_token.replace("Bearer ", "")
        return decode_jwt(auth_token)
    except jwt.ExpiredSignatureError:
        logger.error("Signature expired.")
        return {}
    except jwt.InvalidTokenError:
        logger.error("Invalid token.")
        return {}
