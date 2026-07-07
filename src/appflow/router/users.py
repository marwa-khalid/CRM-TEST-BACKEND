from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from libdata.settings import get_session
from libdata.models.tables import User
from appflow.utils import get_tenant_id

users_router = APIRouter(prefix="/users", tags=["Users"])


def _display_name(user_name: str) -> str:
    """Name = the part of the email before '@'."""
    un = user_name or ""
    return un.split("@")[0] if "@" in un else un


@users_router.get("")
def list_users(db: Session = Depends(get_session), tenant_id=Depends(get_tenant_id)):
    """All users in the tenant — used for @-mention tagging in notes."""
    q = db.query(User).filter(User.is_deleted == False)
    if tenant_id is not None:
        q = q.filter(User.tenant_id == tenant_id)
    users = q.order_by(User.user_name.asc()).all()
    return [
        {"id": u.id, "email": u.user_name, "name": _display_name(u.user_name)}
        for u in users
    ]
