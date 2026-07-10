"""Shared Fleet service helpers."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.deps import handler_name_for_user
from fleet.models.tables import FleetHire


def norm(value) -> str:
    return "" if value is None else str(value)


def get_hire_or_404(db: Session, hire_id: int, tenant_id: Optional[int]) -> FleetHire:
    query = db.query(FleetHire).filter(FleetHire.id == hire_id, FleetHire.is_deleted.isnot(True))
    if tenant_id is not None:
        query = query.filter(FleetHire.tenant_id == tenant_id)
    hire = query.first()
    if not hire:
        raise HTTPException(status_code=404, detail="Hire not found")
    return hire


def actor_name_for(db: Session, actor_id: Optional[int]) -> Optional[str]:
    try:
        return handler_name_for_user(db, actor_id)
    except Exception:  # pylint: disable=broad-exception-caught
        return None
