"""Core Fleet hire service.

This covers the base hire file used by General Details, Driver Details, GDPR,
and the shared field-level audit log. Screen-specific work lives in sibling
services such as document_service, vehicle_service, and pcn_service.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from fleet.models.tables import FleetHire, FleetHireAudit
from fleet.services.common import actor_name_for, get_hire_or_404, norm


def _surname_from(name: Optional[str]) -> str:
    """Last word of the driver's name (Screen 2) — used as the reference prefix."""
    parts = (name or "").strip().split()
    return parts[-1] if parts else ""


def _reference_for(hire: FleetHire) -> str:
    # `FLT-YYYYMM-{id}` on creation (Screen 1); once the driver's surname is
    # known (Screen 2) the FLT prefix is replaced by the surname.
    reference_date = hire.file_opened_at or hire.created_at or datetime.now(timezone.utc)
    prefix = _surname_from(hire.driver_name).upper() or "FLT"
    return f"{prefix}-{reference_date:%Y%m}-{hire.id:03d}"


def _ensure_reference(hire: FleetHire) -> bool:
    """Keep the reference in sync with the current surname (empty until Screen 2)."""
    new_ref = _reference_for(hire)
    if hire.fleet_reference == new_ref:
        return False
    hire.fleet_reference = new_ref
    return True


def create_hire(db: Session, tenant_id: Optional[int], actor_id: Optional[int]) -> FleetHire:
    hire = FleetHire(tenant_id=tenant_id, created_by=actor_id, updated_by=actor_id)
    db.add(hire)
    db.flush()
    _ensure_reference(hire)
    db.commit()
    db.refresh(hire)
    return hire


def list_hires(db: Session, tenant_id: Optional[int]):
    query = db.query(FleetHire).filter(FleetHire.is_deleted.isnot(True))
    if tenant_id is not None:
        query = query.filter(FleetHire.tenant_id == tenant_id)
    hires = query.order_by(FleetHire.id.desc()).all()
    changed = False
    for hire in hires:
        changed = _ensure_reference(hire) or changed
    if changed:
        db.commit()
    return hires


def delete_hire(db: Session, hire_id: int, tenant_id: Optional[int]) -> dict:
    """Soft-delete a hire so it drops off the main list."""
    hire = get_hire_or_404(db, hire_id, tenant_id)
    hire.is_deleted = True
    db.commit()
    return {"success": True}


def get_hire(db: Session, hire_id: int, tenant_id: Optional[int]) -> FleetHire:
    hire = get_hire_or_404(db, hire_id, tenant_id)
    if _ensure_reference(hire):
        db.commit()
        db.refresh(hire)
    return hire


def update_hire(db: Session, hire_id: int, tenant_id: Optional[int], actor_id: Optional[int], data: dict) -> FleetHire:
    """Apply a partial update and log each changed field."""
    hire = get_hire_or_404(db, hire_id, tenant_id)
    _ensure_reference(hire)
    user_name = actor_name_for(db, actor_id)

    for key, value in data.items():
        if not hasattr(hire, key):
            continue
        old = getattr(hire, key)
        if norm(old) == norm(value):
            continue
        db.add(FleetHireAudit(
            hire_id=hire_id,
            user=user_name,
            field_changed=key,
            old_value=norm(old),
            new_value=norm(value),
        ))
        setattr(hire, key, value)

    # Re-sync the reference now that the driver name (surname) may have changed.
    _ensure_reference(hire)
    hire.updated_by = actor_id
    db.commit()
    db.refresh(hire)
    return hire


def list_audit(db: Session, hire_id: int, tenant_id: Optional[int]):
    """Newest-first change log for a hire."""
    get_hire_or_404(db, hire_id, tenant_id)
    return (
        db.query(FleetHireAudit)
        .filter(FleetHireAudit.hire_id == hire_id)
        .order_by(FleetHireAudit.id.desc())
        .all()
    )
