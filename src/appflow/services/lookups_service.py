# app/services/lookups_service.py
from typing import Type, List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from libdata.models.tables import (
    ClaimType, Handler, TargetDebt, CaseStatus, SourceChannel, Prospect, PresentFilePosition, Language, FuelType, Transmission, TaxiType
)

# Simple action labels for audit trail
ACTION_CREATE = "CREATE"
ACTION_UPDATE = "UPDATE"
ACTION_DEACTIVATE = "DEACTIVATE"

# Map friendly entity names for audit logs
ENTITY_NAME = {
    ClaimType: "CLAIM_TYPE",
    Handler: "HANDLER",
    TargetDebt: "TARGET_DEBT",
    CaseStatus: "CASE_STATUS",
    SourceChannel: "SOURCE_CHANNEL",
    Prospect: "PROSPECT",
    PresentFilePosition: "PRESENT_FILE_POSITION",
    Language: "LANGUAGE",
    FuelType: "FUEL_TYPE",
    Transmission: "TRANSMISSION",
    TaxiType: "TAXI_TYPE",
}

LookupModels = (ClaimType, Handler, TargetDebt, CaseStatus, SourceChannel, Prospect, PresentFilePosition, Language, FuelType, Transmission, TaxiType)


# def _audit(db: Session, admin_user_id: Optional[int], model: Type, entity_id: int, action: str, details: Dict[str, Any]):
#     db.add(AuditLog(
#         admin_user_id=admin_user_id,
#         action=action,
#         entity=ENTITY_NAME.get(model, model.__tablename__.upper()),
#         entity_id=entity_id,
#         details=details,
#     ))

def _list_active(db: Session, model: Type) -> List:
    return (db.query(model)
            .filter(model.is_active == True)  # noqa: E712
            .order_by(model.sort_order, model.label)
            .all())


def _list_all(db: Session, model: Type):
    return (db.query(model)
            .order_by(model.is_active.desc(), model.sort_order, model.label)
            .all())


def _get_or_404(db: Session, model: Type, pk: int):
    obj = db.query(model).get(pk)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{ENTITY_NAME.get(model, model.__name__)} not found")
    return obj


def _create(db: Session, model: Type, data: Dict[str, Any], admin_user_id: Optional[int]):
    obj = model(**data, created_by=admin_user_id)
    print(obj)
    db.add(obj)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        # unique (tenant_id, label) violation
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate label for this tenant") from e
    # _audit(db, admin_user_id, model, obj.id, ACTION_CREATE, {"new": data}
    db.refresh(obj)
    return obj


def _update(db: Session, model: Type, pk: int, data: Dict[str, Any], admin_user_id: Optional[int]):
    obj = _get_or_404(db, model, pk)
    old = {k: getattr(obj, k) for k in ("label", "sort_order", "is_active", "tenant_id") if hasattr(obj, k)}
    for k, v in data.items():
        setattr(obj, k, v)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate label for this tenant") from e
    # _audit(db, admin_user_id, model, obj.id, ACTION_UPDATE, {"old": old, "new": data})
    db.refresh(obj)
    return obj


def _deactivate(db: Session, model: Type, pk: int, admin_user_id: Optional[int]):
    obj = _get_or_404(db, model, pk)
    if not obj.is_active:
        return obj
    obj.is_active = False
    db.flush()
    # _audit(db, admin_user_id, model, obj.id, ACTION_DEACTIVATE, {"new": {"is_active": False}})
    db.refresh(obj)
    return obj


# --------- Public list helpers (UI) -----------
def list_claim_types(db: Session): return _list_active(db, ClaimType)


def list_handlers(db: Session): return _list_active(db, Handler)


def list_target_debts(db: Session): return _list_active(db, TargetDebt)


def list_case_statuses(db: Session): return _list_active(db, CaseStatus)


def list_source_channels(db: Session): return _list_active(db, SourceChannel)


def list_prospects(db: Session): return _list_active(db, Prospect)


def list_present_positions(db: Session): return _list_active(db, PresentFilePosition)


def list_languages(db: Session): return _list_active(db, Language)

def list_fuel_types(db: Session): return _list_active(db, FuelType)

def list_transmissions(db: Session): return _list_active(db, Transmission)

def list_taxi_types(db: Session): return  _list_active(db, TaxiType)

# --------- Admin list helpers -----------------
def listall_claim_types(db: Session): return _list_all(db, ClaimType)


def listall_handlers(db: Session): return _list_all(db, Handler)


def listall_target_debts(db: Session): return _list_all(db, TargetDebt)


def listall_case_statuses(db: Session): return _list_all(db, CaseStatus)


def listall_source_channels(db: Session): return _list_all(db, SourceChannel)


def listall_prospects(db: Session): return _list_all(db, Prospect)


def listall_present_positions(db: Session): return _list_all(db, PresentFilePosition)


def listall_languages(db: Session): return _list_all(db, Language)

def listall_fuel_types(db: Session): return _list_all(db, FuelType)

def listall_transmissions(db: Session): return _list_all(db, Transmission)

def listall_taxi_types(db: Session): return _list_all(db, TaxiType)

# --------- Admin CRUD -------------------------
def create_claim_type(db, data, admin_id): return _create(db, ClaimType, data, admin_id)


def update_claim_type(db, pk, data, admin_id): return _update(db, ClaimType, pk, data, admin_id)


def deactivate_claim_type(db, pk, admin_id): return _deactivate(db, ClaimType, pk, admin_id)


def create_handler(db, data, admin_id): return _create(db, Handler, data, admin_id)


def update_handler(db, pk, data, admin_id): return _update(db, Handler, pk, data, admin_id)


def deactivate_handler(db, pk, admin_id): return _deactivate(db, Handler, pk, admin_id)


def create_target_debt(db, data, admin_id): return _create(db, TargetDebt, data, admin_id)


def update_target_debt(db, pk, data, admin_id): return _update(db, TargetDebt, pk, data, admin_id)


def deactivate_target_debt(db, pk, admin_id): return _deactivate(db, TargetDebt, pk, admin_id)


def create_case_status(db, data, admin_id): return _create(db, CaseStatus, data, admin_id)


def update_case_status(db, pk, data, admin_id): return _update(db, CaseStatus, pk, data, admin_id)


def deactivate_case_status(db, pk, admin_id): return _deactivate(db, CaseStatus, pk, admin_id)


def create_source_channel(db, data, admin_id): return _create(db, SourceChannel, data, admin_id)


def update_source_channel(db, pk, data, admin_id): return _update(db, SourceChannel, pk, data, admin_id)


def deactivate_source_channel(db, pk, admin_id): return _deactivate(db, SourceChannel, pk, admin_id)


def create_prospect(db, data, admin_id): return _create(db, Prospect, data, admin_id)


def update_prospect(db, pk, data, admin_id): return _update(db, Prospect, pk, data, admin_id)


def deactivate_prospect(db, pk, admin_id): return _deactivate(db, Prospect, pk, admin_id)


def create_present_position(db, data, admin_id): return _create(db, PresentFilePosition, data, admin_id)


def update_present_position(db, pk, data, admin_id): return _update(db, PresentFilePosition, pk, data, admin_id)


def deactivate_present_position(db, pk, admin_id): return _deactivate(db, PresentFilePosition, pk, admin_id)


def create_language(db, data, admin_id): return _create(db, Language, data, admin_id)


def update_language(db, pk, data, admin_id): return _update(db, Language, pk, data, admin_id)


def deactivate_language(db, pk, admin_id): return _deactivate(db, Language, pk, admin_id)


def create_fuel_type(db, data, admin_id): return _create(db, FuelType, data, admin_id)


def update_fuel_type(db, pk, data, admin_id): return _update(db, FuelType, pk, data, admin_id)


def deactivate_fuel_type(db, pk, admin_id): return _deactivate(db, FuelType, pk, admin_id)


def create_transmission(db, data, admin_id): return _create(db, Transmission, data, admin_id)


def update_transmission(db, pk, data, admin_id): return _update(db, Transmission, pk, data, admin_id)


def deactivate_transmission(db, pk, admin_id): return _deactivate(db, Transmission, pk, admin_id)


def create_taxi_type(db, data, admin_id): return _create(db, TaxiType, data, admin_id)


def update_taxi_type(db, pk, data, admin_id): return _update(db, TaxiType, pk, data, admin_id)


def deactivate_taxi_type(db, pk, admin_id): return _deactivate(db, TaxiType, pk, admin_id)
