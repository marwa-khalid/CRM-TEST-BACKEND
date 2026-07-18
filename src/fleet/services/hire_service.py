"""Core Fleet hire service.

This covers the base hire file used by General Details, Driver Details, GDPR,
and the shared field-level audit log. Screen-specific work lives in sibling
services such as document_service, vehicle_service, and pcn_service.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from fleet.models.tables import FleetHire, FleetHireAudit, FleetHireDocument, FleetHireVehicle, FleetPcn
from fleet.services.common import actor_name_for, get_hire_or_404, norm


def _surname_from(name: Optional[str]) -> str:
    """Last word of the driver's name (Screen 2) — used as the reference prefix."""
    parts = (name or "").strip().split()
    return parts[-1] if parts else ""


def _reference_for(hire: FleetHire) -> str:
    # `SK-{SURNAME}-{id}` (Skyline). The date part is dropped so Fleet references
    # never collide with the Claims format. Until the driver's surname is known
    # (Screen 2) it's just `SK-{id}`; it fills in live once the surname is saved.
    surname = _surname_from(hire.driver_name).upper()
    return f"SK-{surname}-{hire.id}" if surname else f"SK-{hire.id}"


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

    # Derive each hire's last-vehicle hire_status (the most recently added vehicle
    # on the Hire Vehicle Details screen) for the On/Off Hire listing widgets.
    hire_ids = [h.id for h in hires]
    last_status: dict[int, Optional[str]] = {}
    last_reg: dict[int, Optional[str]] = {}
    if hire_ids:
        vehicles = (
            db.query(FleetHireVehicle)
            .filter(FleetHireVehicle.hire_id.in_(hire_ids))
            .order_by(FleetHireVehicle.hire_id, FleetHireVehicle.position, FleetHireVehicle.id)
            .all()
        )
        # ascending order → the last row seen per hire is the latest vehicle
        for v in vehicles:
            last_status[v.hire_id] = v.hire_status
            last_reg[v.hire_id] = v.registration_number
    for hire in hires:
        hire.last_vehicle_hire_status = last_status.get(hire.id)
        hire.last_vehicle_registration = last_reg.get(hire.id)
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


def _filled_count(obj, fields: list[str]) -> int:
    if not obj:
        return 0
    return sum(
        1
        for field in fields
        if getattr(obj, field, None) is not None and str(getattr(obj, field, "")).strip() != ""
    )


def _is_proof_address_doc(doc_type: str) -> bool:
    return (
        doc_type.startswith("bank_statement_")
        or doc_type.startswith("utility_")
        or doc_type in {"firstUtility", "secondUtility"}
    )


def _matches_checklist_doc(doc_type: str, checklist_key: str) -> bool:
    if doc_type == checklist_key:
        return True
    if checklist_key == "checklist_bank_statement":
        return doc_type.startswith("bank_statement_")
    if checklist_key == "checklist_utility_bill":
        return doc_type.startswith("utility_") or doc_type in {"firstUtility", "secondUtility"}
    if checklist_key == "checklist_dl_front":
        return doc_type in {"driving_licence", "dlFront"}
    if checklist_key == "checklist_dl_back":
        return doc_type == "dlBack"
    return False


def completion_summary(db: Session, hire_id: int, tenant_id: Optional[int]) -> dict:
    """Small payload for sidebar completion dots. Avoids loading the full
    vehicle/document/PCN records in the parent Add Hire page on every step."""
    get_hire_or_404(db, hire_id, tenant_id)

    vehicle_fields = ["registration_number", "make", "model", "transmission", "hire_status"]
    pcn_fields = [
        "council_name",
        "council_address",
        "council_postcode",
        "pcn_number",
        "offence_date",
        "pcn_status",
        "liability_transfer_status",
        "response_deadline",
    ]
    checklist_required = [
        "checklist_bank_statement",
        "checklist_utility_bill",
        "checklist_dl_front",
        "checklist_dl_back",
        "checklist_taxi_badge",
        "checklist_signed_rental_contract",
        "checklist_signed_checkout_sheet",
        "checklist_signed_checkin_sheet",
    ]

    vehicle = (
        db.query(FleetHireVehicle)
        .filter(FleetHireVehicle.hire_id == hire_id)
        .order_by(FleetHireVehicle.position, FleetHireVehicle.id)
        .first()
    )
    documents = db.query(FleetHireDocument.doc_type).filter(FleetHireDocument.hire_id == hire_id).all()
    doc_types = [row[0] for row in documents]
    pcn = db.query(FleetPcn).filter(FleetPcn.hire_id == hire_id).first()

    proof_present = len([present for present in [
        any(_is_proof_address_doc(doc_type) for doc_type in doc_types),
        any(doc_type == "dlFront" for doc_type in doc_types),
        any(doc_type == "dlBack" for doc_type in doc_types),
    ] if present])
    document_present = sum(
        1
        for required in checklist_required
        if any(_matches_checklist_doc(doc_type, required) for doc_type in doc_types)
    )

    return {
        "vehicle_present": _filled_count(vehicle, vehicle_fields),
        "vehicle_total": len(vehicle_fields),
        "proof_present": proof_present,
        "proof_total": 3,
        "document_present": document_present,
        "document_total": len(checklist_required),
        "pcn_present": _filled_count(pcn, pcn_fields),
        "pcn_total": len(pcn_fields),
    }
