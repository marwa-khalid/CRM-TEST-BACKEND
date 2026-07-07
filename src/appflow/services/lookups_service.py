# app/services/lookups_service.py
from typing import Type, List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from fastapi import HTTPException, status

from libdata.models.tables import (
    ClaimType, Handler, TargetDebt, CaseStatus, SourceChannel, Prospect, PresentFilePosition, Language, FuelType, Transmission, TaxiType,
    SalvageCategory,KeepingSalvage,PavAgreed,RetainingSalvage,PolicyType,CoverLevel,ReasonMid,LiabilityStance,SettlementStatus,VehicleStatus,
    ClientVehicleCategory,ActualVehicleCategory,AdminFeeType,HireVehicleStatus
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
    SalvageCategory: "SALVAGE_CATEGORY",
    KeepingSalvage: "KEEPING_SALVAGE",
    PavAgreed: "PAV_AGREED",
    RetainingSalvage: "RETAINING_SALVAGE",
    PolicyType: "POLICY_TYPE",
    CoverLevel: "COVER_LEVEL",
    ReasonMid: "Reason_Mid",
    LiabilityStance: "Liability_Stance",
    SettlementStatus: "Settlement_Status",
    VehicleStatus: "Vehicle_Status",
    ClientVehicleCategory: "Client_Vehicle_Category",
    ActualVehicleCategory: "Actual_Vehicle_Category",
    AdminFeeType: "Admin_Fee_Type",
    HireVehicleStatus: "Hire_Vehicle_Status"
}

LookupModels = (ClaimType, Handler, TargetDebt, CaseStatus, SourceChannel, Prospect, PresentFilePosition, Language, FuelType, Transmission, TaxiType, SalvageCategory,KeepingSalvage,PavAgreed,RetainingSalvage,PolicyType,CoverLevel,ReasonMid,LiabilityStance,SettlementStatus,VehicleStatus,ClientVehicleCategory,ActualVehicleCategory,AdminFeeType,HireVehicleStatus)


# def _audit(db: Session, admin_user_id: Optional[int], model: Type, entity_id: int, action: str, details: Dict[str, Any]):
#     db.add(AuditLog(
#         admin_user_id=admin_user_id,
#         action=action,
#         entity=ENTITY_NAME.get(model, model.__tablename__.upper()),
#         entity_id=entity_id,
#         details=details,
#     ))

def _list_active(db: Session, model: Type) -> List:
    # Dropdowns are shown alphabetically by label across all screens.
    return (db.query(model)
            .filter(model.is_active == True)  # noqa: E712
            .order_by(func.lower(model.label))
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

def list_salvage_categories(db: Session): return  _list_active(db, SalvageCategory)

def list_keeping_salvages(db: Session): return  _list_active(db, KeepingSalvage)

def list_pav_agrees(db: Session): return  _list_active(db, PavAgreed)

def list_retaining_salvages(db: Session): return  _list_active(db, RetainingSalvage)

def list_policy_types(db: Session): return _list_active(db, PolicyType)

def list_cover_levels(db: Session): return _list_active(db, CoverLevel)

def list_mid_reasons(db: Session): return  _list_active(db, ReasonMid)

def list_liability_stances(db: Session): return _list_active(db, LiabilityStance)

def list_settlement_statuses(db: Session): return _list_active(db, SettlementStatus)
def list_vehicle_statuses(db: Session): return _list_active(db, VehicleStatus)

def list_client_vehicle_categories(db: Session): return _list_active(db, ClientVehicleCategory)

def list_actual_vehicle_categories(db: Session): return _list_active(db, ActualVehicleCategory)

def list_admin_fee_types(db: Session): return _list_active(db, AdminFeeType)

def list_hire_vehicle_statuses(db: Session): return _list_active(db, HireVehicleStatus)
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

def listall_salvage_categories(db: Session): return _list_all(db, SalvageCategory)

def listall_keeping_salvages(db: Session): return _list_all(db, KeepingSalvage)

def listall_pav_agrees(db: Session): return _list_all(db, PavAgreed)

def listall_retaining_salvages(db: Session): return _list_all(db, RetainingSalvage)

def listall_policy_types(db: Session): return _list_all(db, PolicyType)

def listall_cover_levels(db: Session): return _list_all(db, CoverLevel)

def listall_mid_reasons(db: Session): return _list_all(db, ReasonMid)

def listall_liability_stances(db: Session): return _list_all(db, LiabilityStance)

def listall_settlement_statuses(db: Session): return _list_all(db, SettlementStatus)
def listall_vehicle_statuses(db: Session): return _list_all(db, VehicleStatus)

def listall_client_vehicle_categories(db: Session): return _list_all(db, ClientVehicleCategory)

def listall_actual_vehicle_categories(db: Session): return _list_all(db, ActualVehicleCategory)

def listall_admin_fee_types(db: Session): return _list_all(db, AdminFeeType)

def listall_hire_vehicle_statuses(db: Session): return _list_all(db, HireVehicleStatus)
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


def create_salvage_category(db, data, admin_id): return _create(db, SalvageCategory, data, admin_id)


def update_salvage_category(db, pk, data, admin_id): return _update(db, SalvageCategory, pk, data, admin_id)


def deactivate_salvage_category(db, pk, admin_id): return _deactivate(db, SalvageCategory, pk, admin_id)


def create_keeping_salvage(db, data, admin_id): return _create(db, KeepingSalvage, data, admin_id)


def update_keeping_salvage(db, pk, data, admin_id): return _update(db, KeepingSalvage, pk, data, admin_id)


def deactivate_keeping_salvage(db, pk, admin_id): return _deactivate(db, KeepingSalvage, pk, admin_id)


def create_pav_agree(db, data, admin_id): return _create(db, PavAgreed, data, admin_id)


def update_pav_agree(db, pk, data, admin_id): return _update(db, PavAgreed, pk, data, admin_id)


def deactivate_pav_agree(db, pk, admin_id): return _deactivate(db, PavAgreed, pk, admin_id)


def create_retaining_salvage(db, data, admin_id): return _create(db, RetainingSalvage, data, admin_id)


def update_retaining_salvage(db, pk, data, admin_id): return _update(db, RetainingSalvage, pk, data, admin_id)


def deactivate_retaining_salvage(db, pk, admin_id): return _deactivate(db, RetainingSalvage, pk, admin_id)


def create_policy_type(db, data, admin_id): return _create(db, PolicyType, data, admin_id)


def update_policy_type(db, pk, data, admin_id): return _update(db, PolicyType, pk, data, admin_id)


def deactivate_policy_type(db, pk, admin_id): return _deactivate(db, PolicyType, pk, admin_id)


def create_cover_level(db, data, admin_id): return _create(db, CoverLevel, data, admin_id)


def update_cover_level(db, pk, data, admin_id): return _update(db, CoverLevel, pk, data, admin_id)


def deactivate_cover_level(db, pk, admin_id): return _deactivate(db, CoverLevel, pk, admin_id)


def create_mid_reason(db, data, admin_id): return _create(db, ReasonMid, data, admin_id)


def update_mid_reason(db, pk, data, admin_id): return _update(db, ReasonMid, pk, data, admin_id)


def deactivate_mid_reason(db, pk, admin_id): return _deactivate(db, ReasonMid, pk, admin_id)


def create_liability_stance(db, data, admin_id): return _create(db, LiabilityStance, data, admin_id)


def update_liability_stance(db, pk, data, admin_id): return _update(db, LiabilityStance, pk, data, admin_id)


def deactivate_liability_stance(db, pk, admin_id): return _deactivate(db, LiabilityStance, pk, admin_id)


def create_settlement_status(db, data, admin_id): return _create(db, SettlementStatus, data, admin_id)


def update_settlement_status(db, pk, data, admin_id): return _update(db, SettlementStatus, pk, data, admin_id)


def deactivate_settlement_status(db, pk, admin_id): return _deactivate(db, SettlementStatus, pk, admin_id)
def create_vehicle_status(db, data, admin_id): return _create(db, VehicleStatus, data, admin_id)
def update_vehicle_status(db, pk, data, admin_id): return _update(db, VehicleStatus, pk, data, admin_id)
def deactivate_vehicle_status(db, pk, admin_id): return _deactivate(db, VehicleStatus, pk, admin_id)

def create_client_vehicle_category(db, data, admin_id): return _create(db, ClientVehicleCategory, data, admin_id)


def update_client_vehicle_category(db, pk, data, admin_id): return _update(db, ClientVehicleCategory, pk, data, admin_id)


def deactivate_client_vehicle_category(db, pk, admin_id): return _deactivate(db, ClientVehicleCategory, pk, admin_id)


def create_actual_vehicle_category(db, data, admin_id): return _create(db, ActualVehicleCategory, data, admin_id)


def update_actual_vehicle_category(db, pk, data, admin_id): return _update(db, ActualVehicleCategory, pk, data, admin_id)


def deactivate_actual_vehicle_category(db, pk, admin_id): return _deactivate(db, ActualVehicleCategory, pk, admin_id)


def create_admin_fee_type(db, data, admin_id): return _create(db, AdminFeeType, data, admin_id)


def update_admin_fee_type(db, pk, data, admin_id): return _update(db, AdminFeeType, pk, data, admin_id)


def deactivate_admin_fee_type(db, pk, admin_id): return _deactivate(db, AdminFeeType, pk, admin_id)


def create_hire_vehicle_status(db, data, admin_id): return _create(db, HireVehicleStatus, data, admin_id)


def update_hire_vehicle_status(db, pk, data, admin_id): return _update(db, HireVehicleStatus, pk, data, admin_id)


def deactivate_hire_vehicle_status(db, pk, admin_id): return _deactivate(db, HireVehicleStatus, pk, admin_id)
