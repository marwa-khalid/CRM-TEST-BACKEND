from typing import Optional
from fastapi import Request


def get_tenant_id(request:Request):
    return request.state.tenant_id

def actor_id(request: Request) -> Optional[int]:
    try:
        return request.state.user_id
    except Exception:
        return None