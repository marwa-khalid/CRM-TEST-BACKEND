from fastapi import HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer
from appflow.logger import logger
from .token_util import decode_auth_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/verify", auto_error=False)


async def authenticate(
    request: Request,
    auth_token: str = Depends(oauth2_scheme),
):
    pass
    logger.info(f"auth_token: {auth_token}")

    user_details = decode_auth_token(auth_token)
    logger.info(f'user_details: {user_details}')
    if user_details:
        request.state.user_id = user_details.get('user_id')
        request.state.tenant_id = user_details.get('tenant_id')
        request.state.user_name = user_details.get('user_name')
        return user_details
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
