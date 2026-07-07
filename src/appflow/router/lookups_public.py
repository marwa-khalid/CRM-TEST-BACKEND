from typing import List, Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from appflow.models.lookups import (
    ClaimTypeIn, ClaimTypeOut,
    HandlerIn, HandlerOut,
    TargetDebtIn, TargetDebtOut,
    CaseStatusIn, CaseStatusOut,
    SourceChannelIn, SourceChannelOut,
    ProspectIn, ProspectOut,
    PresentFilePositionIn, PresentFilePositionOut, LanguageIn, LanguageOut,
    FuelTypeIn,FuelTypeOut,TransmissionIn,TransmissionOut,TaxiTypeIn,TaxiTypeOut,
    SalvageCategoryIn,SalvageCategoryOut,KeepingSalvageIn,KeepingSalvageOut,PavAgreeIn,PavAgreeOut,RetainingSalvageIn,RetainingSalvageOut,
    PolicyTypeIn,PolicyTypeOut,CoverLevelIn,CoverLevelOut,ReasonMidIn,ReasonMidOut,LiabilityStanceIn,LiabilityStanceOut,    SettlementStatusIn,
    SettlementStatusOut, VehicleStatusIn, VehicleStatusOut,ClientVehicleCategoryIn,ClientVehicleCategoryOut,ActualVehicleCategoryIn,ActualVehicleCategoryOut,AdminFeeTypeIn,AdminFeeTypeOut,
    HireVehicleStatusIn,HireVehicleStatusOut
)
from appflow.services.lookups_service import (
    # list (active only)
    list_claim_types, list_handlers, list_target_debts, list_case_statuses,
    list_source_channels, list_prospects, list_present_positions, list_languages,list_fuel_types,list_transmissions,list_taxi_types,list_salvage_categories,list_keeping_salvages,list_pav_agrees,list_retaining_salvages,
    list_policy_types,list_cover_levels,list_mid_reasons,list_liability_stances,list_settlement_statuses, list_vehicle_statuses,list_client_vehicle_categories,list_actual_vehicle_categories,list_admin_fee_types,list_hire_vehicle_statuses,
    # list all (admin view)
    listall_claim_types, listall_handlers, listall_target_debts, listall_case_statuses,
    listall_source_channels, listall_prospects, listall_present_positions, listall_languages,listall_fuel_types,listall_transmissions,listall_taxi_types,listall_salvage_categories,listall_keeping_salvages,listall_pav_agrees,listall_retaining_salvages,
    listall_policy_types,listall_cover_levels,listall_mid_reasons,listall_liability_stances,listall_settlement_statuses, listall_vehicle_statuses,listall_client_vehicle_categories,listall_actual_vehicle_categories,listall_admin_fee_types,listall_hire_vehicle_statuses,
    # CRUD
    create_claim_type, update_claim_type, deactivate_claim_type,
    create_handler, update_handler, deactivate_handler,
    create_target_debt, update_target_debt, deactivate_target_debt,
    create_case_status, update_case_status, deactivate_case_status,
    create_source_channel, update_source_channel, deactivate_source_channel,
    create_prospect, update_prospect, deactivate_prospect,
    create_present_position, update_present_position, deactivate_present_position, create_language, update_language,
    deactivate_language,create_fuel_type,update_fuel_type,deactivate_fuel_type,
    create_transmission,update_transmission,deactivate_transmission,create_taxi_type,update_taxi_type,deactivate_taxi_type,
    create_salvage_category,update_salvage_category,deactivate_salvage_category,create_keeping_salvage,update_keeping_salvage,deactivate_keeping_salvage,
    create_pav_agree,update_pav_agree,deactivate_pav_agree,create_retaining_salvage,update_retaining_salvage,deactivate_retaining_salvage,
    create_policy_type,update_policy_type,deactivate_policy_type,create_cover_level,update_cover_level,deactivate_cover_level,
    create_mid_reason,update_mid_reason,deactivate_mid_reason,create_liability_stance,update_liability_stance,deactivate_liability_stance,
    create_settlement_status,update_settlement_status,deactivate_settlement_status, create_vehicle_status, update_vehicle_status, deactivate_vehicle_status,
    create_client_vehicle_category,update_client_vehicle_category,deactivate_client_vehicle_category,create_actual_vehicle_category,update_actual_vehicle_category,deactivate_actual_vehicle_category,
    create_admin_fee_type,update_admin_fee_type,deactivate_admin_fee_type,create_hire_vehicle_status,update_hire_vehicle_status,deactivate_hire_vehicle_status
)
from libdata.settings import get_session
from appflow.utils import actor_id, get_tenant_id


lookup_router = APIRouter(prefix="/setups", tags=["Lookups"])


# ---------------- Claim Types ----------------
@lookup_router.get("/claim-types", response_model=List[ClaimTypeOut])
def get_claim_types(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_claim_types(db) if include_inactive else list_claim_types(db)


@lookup_router.post("/claim-types", response_model=ClaimTypeOut)
def create_claim_type_route(payload: ClaimTypeIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_claim_type(db, data, actor_id(request))
    return ClaimTypeOut.from_orm(obj)


@lookup_router.put("/claim-types/{pk}", response_model=ClaimTypeOut)
def update_claim_type_route(pk: int, payload: ClaimTypeIn, request: Request, db: Session = Depends(get_session)):
    obj = update_claim_type(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return ClaimTypeOut.from_orm(obj)


@lookup_router.patch("/claim-types/{pk}/deactivate", response_model=ClaimTypeOut)
def deactivate_claim_type_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_claim_type(db, pk, actor_id(request))
    return ClaimTypeOut.from_orm(obj)


# ---------------- Handlers -------------------
@lookup_router.get("/handlers", response_model=List[HandlerOut])
def get_handlers(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_handlers(db) if include_inactive else list_handlers(db)


@lookup_router.post("/handlers", response_model=HandlerOut)
def create_handler_route(payload: HandlerIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_handler(db, data, actor_id(request))
    return HandlerOut.from_orm(obj)


@lookup_router.put("/handlers/{pk}", response_model=HandlerOut)
def update_handler_route(pk: int, payload: HandlerIn, request: Request, db: Session = Depends(get_session)):
    obj = update_handler(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return HandlerOut.from_orm(obj)


@lookup_router.patch("/handlers/{pk}/deactivate", response_model=HandlerOut)
def deactivate_handler_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_handler(db, pk, actor_id(request))
    return HandlerOut.from_orm(obj)


# -------------- Target Debts -----------------
@lookup_router.get("/target-debts", response_model=List[TargetDebtOut])
def get_target_debts(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_target_debts(db) if include_inactive else list_target_debts(db)


@lookup_router.post("/target-debts", response_model=TargetDebtOut)
def create_target_debt_route(payload: TargetDebtIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_target_debt(db, data, actor_id(request))
    return TargetDebtOut.from_orm(obj)


@lookup_router.put("/target-debts/{pk}", response_model=TargetDebtOut)
def update_target_debt_route(pk: int, payload: TargetDebtIn, request: Request, db: Session = Depends(get_session)):
    obj = update_target_debt(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return TargetDebtOut.from_orm(obj)


@lookup_router.patch("/target-debts/{pk}/deactivate", response_model=TargetDebtOut)
def deactivate_target_debt_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_target_debt(db, pk, actor_id(request))
    return TargetDebtOut.from_orm(obj)


# -------------- Case Statuses ----------------
@lookup_router.get("/case-statuses", response_model=List[CaseStatusOut])
def get_case_statuses(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_case_statuses(db) if include_inactive else list_case_statuses(db)


@lookup_router.post("/case-statuses", response_model=CaseStatusOut)
def create_case_status_route(payload: CaseStatusIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_case_status(db, data, actor_id(request))
    return CaseStatusOut.from_orm(obj)


@lookup_router.put("/case-statuses/{pk}", response_model=CaseStatusOut)
def update_case_status_route(pk: int, payload: CaseStatusIn, request: Request, db: Session = Depends(get_session)):
    obj = update_case_status(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return CaseStatusOut.from_orm(obj)


@lookup_router.patch("/case-statuses/{pk}/deactivate", response_model=CaseStatusOut)
def deactivate_case_status_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_case_status(db, pk, actor_id(request))
    return CaseStatusOut.from_orm(obj)


# -------------- Source Channels --------------
@lookup_router.get("/source-channels", response_model=List[SourceChannelOut])
def get_source_channels(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_source_channels(db) if include_inactive else list_source_channels(db)


@lookup_router.post("/source-channels", response_model=SourceChannelOut)
def create_source_channel_route(payload: SourceChannelIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_source_channel(db, data, actor_id(request))
    return SourceChannelOut.from_orm(obj)


@lookup_router.put("/source-channels/{pk}", response_model=SourceChannelOut)
def update_source_channel_route(pk: int, payload: SourceChannelIn, request: Request,
                                db: Session = Depends(get_session)):
    obj = update_source_channel(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return SourceChannelOut.from_orm(obj)


@lookup_router.patch("/source-channels/{pk}/deactivate", response_model=SourceChannelOut)
def deactivate_source_channel_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_source_channel(db, pk, actor_id(request))
    return SourceChannelOut.from_orm(obj)


# ---------------- Prospects ------------------
@lookup_router.get("/prospects", response_model=List[ProspectOut])
def get_prospects(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_prospects(db) if include_inactive else list_prospects(db)


@lookup_router.post("/prospects", response_model=ProspectOut)
def create_prospect_route(payload: ProspectIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_prospect(db, data, actor_id(request))
    return ProspectOut.from_orm(obj)


@lookup_router.put("/prospects/{pk}", response_model=ProspectOut)
def update_prospect_route(pk: int, payload: ProspectIn, request: Request, db: Session = Depends(get_session)):
    obj = update_prospect(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return ProspectOut.from_orm(obj)


@lookup_router.patch("/prospects/{pk}/deactivate", response_model=ProspectOut)
def deactivate_prospect_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_prospect(db, pk, actor_id(request))
    return ProspectOut.from_orm(obj)


# --------- Present File Positions ----------
@lookup_router.get("/present-file-positions", response_model=List[PresentFilePositionOut])
def get_present_positions(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_present_positions(db) if include_inactive else list_present_positions(db)


@lookup_router.post("/present-file-positions", response_model=PresentFilePositionOut)
def create_present_position_route(payload: PresentFilePositionIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_present_position(db, data, actor_id(request))
    return PresentFilePositionOut.from_orm(obj)


@lookup_router.put("/present-file-positions/{pk}", response_model=PresentFilePositionOut)
def update_present_position_route(pk: int, payload: PresentFilePositionIn, request: Request,
                                  db: Session = Depends(get_session)):
    obj = update_present_position(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    obj = update_present_position(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return PresentFilePositionOut.from_orm(obj)


@lookup_router.patch("/present-file-positions/{pk}/deactivate", response_model=PresentFilePositionOut)
def deactivate_present_position_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_present_position(db, pk, actor_id(request))
    return PresentFilePositionOut.from_orm(obj)


# --------- Language ----------
@lookup_router.get("/languages", response_model=List[LanguageOut])
def get_languages(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_languages(db) if include_inactive else list_languages(db)


@lookup_router.post("/languages", response_model=LanguageOut)
def create_language_router(payload: LanguageIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_language(db, data, actor_id(request))
    return LanguageOut.from_orm(obj)


@lookup_router.put("/languages/{pk}", response_model=LanguageOut)
def update_language_route(pk: int, payload: LanguageIn, request: Request, db: Session = Depends(get_session)):
    obj = update_language(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    obj = update_language(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return LanguageOut.from_orm(obj)


@lookup_router.patch("/languages/{pk}/deactivate", response_model=LanguageOut)
def deactivate_language_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_language(db, pk, actor_id(request))
    return LanguageOut.from_orm(obj)

# --------- Fuel Type ----------
@lookup_router.get("/fuel-types", response_model=List[FuelTypeOut])
def get_fuel_types(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_fuel_types(db) if include_inactive else list_fuel_types(db)

@lookup_router.post("/fuel-types", response_model=FuelTypeOut)
def create_fuel_type_route(payload: FuelTypeIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_fuel_type(db, data, actor_id(request))
    return FuelTypeOut.from_orm(obj)

@lookup_router.put("/fuel-types/{pk}", response_model=FuelTypeOut)
def update_fuel_type_route(pk: int, payload: FuelTypeIn, request: Request, db: Session = Depends(get_session)):
    obj = update_fuel_type(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return FuelTypeOut.from_orm(obj)

@lookup_router.patch("/fuel-types/{pk}/deactivate", response_model=FuelTypeOut)
def deactivate_fuel_type_route(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_fuel_type(db, pk, actor_id(request))
    return FuelTypeOut.from_orm(obj)

# --------- Transmission ----------
@lookup_router.get("/transmissions", response_model=List[TransmissionOut])
def get_transmission_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_transmissions(db) if include_inactive else list_transmissions(db)

@lookup_router.post("/transmissions", response_model=TransmissionOut)
def create_transmission_router(payload: FuelTypeIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_transmission(db, data, actor_id(request))
    return TransmissionOut.from_orm(obj)

@lookup_router.put("/transmissions/{pk}", response_model=TransmissionOut)
def update_transmission_router(pk: int, payload: TransmissionIn, request: Request, db: Session = Depends(get_session)):
    obj = update_transmission(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return TransmissionOut.from_orm(obj)

@lookup_router.patch("/transmissions/{pk}/deactivate", response_model=TransmissionOut)
def deactivate_transmission_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_transmission(db, pk, actor_id(request))
    return TransmissionOut.from_orm(obj)

# --------- TAXI TYPE ----------
@lookup_router.get("/taxi-types", response_model=List[TaxiTypeOut])
def get_taxi_type_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_taxi_types(db) if include_inactive else list_taxi_types(db)

@lookup_router.post("/taxi-types", response_model=TaxiTypeOut)
def create_taxi_type_router(payload: TaxiTypeIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_taxi_type(db, data, actor_id(request))
    return TaxiTypeOut.from_orm(obj)

@lookup_router.put("/taxi-types/{pk}", response_model=TaxiTypeOut)
def update_taxi_type_router(pk: int, payload: TaxiTypeIn, request: Request, db: Session = Depends(get_session)):
    obj = update_taxi_type(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return TaxiTypeOut.from_orm(obj)

@lookup_router.patch("/taxi-types/{pk}/deactivate", response_model=TaxiTypeOut)
def deactivate_taxi_type_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_taxi_type(db, pk, actor_id(request))
    return TaxiTypeOut.from_orm(obj)

# ---------------- Salvage Category ------------------
@lookup_router.get("/salvage_categories", response_model=List[SalvageCategoryOut])
def get_salvage_category_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_salvage_categories(db) if include_inactive else list_salvage_categories(db)

@lookup_router.post("/salvage_categories", response_model=SalvageCategoryOut)
def create_salvage_category_router(payload: SalvageCategoryIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_salvage_category(db, data, actor_id(request))
    return SalvageCategoryOut.from_orm(obj)

@lookup_router.put("/salvage_categories/{pk}", response_model=SalvageCategoryOut)
def update_salvage_category_router(pk: int, payload: SalvageCategoryIn, request: Request, db: Session = Depends(get_session)):
    obj = update_salvage_category(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return SalvageCategoryOut.from_orm(obj)

@lookup_router.patch("/salvage_categories/{pk}/deactivate", response_model=SalvageCategoryOut)
def deactivate_salvage_category_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_salvage_category(db, pk, actor_id(request))
    return SalvageCategoryOut.from_orm(obj)
# ---------------- Keeping Salvage ------------------
@lookup_router.get("/keeping_salvages", response_model=List[KeepingSalvageOut])
def get_keeping_salvage_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_keeping_salvages(db) if include_inactive else list_keeping_salvages(db)

@lookup_router.post("/keeping_salvages", response_model=KeepingSalvageOut)
def create_keeping_salvage_router(payload: KeepingSalvageIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_keeping_salvage(db, data, actor_id(request))
    return KeepingSalvageOut.from_orm(obj)

@lookup_router.put("/keeping_salvages/{pk}", response_model=KeepingSalvageOut)
def update_keeping_salvage_router(pk: int, payload: KeepingSalvageIn, request: Request, db: Session = Depends(get_session)):
    obj = update_keeping_salvage(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return KeepingSalvageOut.from_orm(obj)

@lookup_router.patch("/keeping_salvages/{pk}/deactivate", response_model=KeepingSalvageOut)
def deactivate_keeping_salvage_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_keeping_salvage(db, pk, actor_id(request))
    return KeepingSalvageOut.from_orm(obj)
# ---------------- Pav Agree ------------------
@lookup_router.get("/pav_agrees", response_model=List[PavAgreeOut])
def get_pav_agree_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_pav_agrees(db) if include_inactive else list_pav_agrees(db)

@lookup_router.post("/pav_agrees", response_model=PavAgreeOut)
def create_pav_agree_router(payload: PavAgreeIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_pav_agree(db, data, actor_id(request))
    return PavAgreeOut.from_orm(obj)

@lookup_router.put("/pav_agrees/{pk}", response_model=PavAgreeOut)
def update_pav_agree_router(pk: int, payload: PavAgreeIn, request: Request, db: Session = Depends(get_session)):
    obj = update_pav_agree(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return PavAgreeOut.from_orm(obj)

@lookup_router.patch("/pav_agrees/{pk}/deactivate", response_model=PavAgreeOut)
def deactivate_pav_agree_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_pav_agree(db, pk, actor_id(request))
    return PavAgreeOut.from_orm(obj)
# ---------------- Retaining Salvages ------------------
@lookup_router.get("/retaining_salvages", response_model=List[RetainingSalvageOut])
def get_retaining_salvage_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_retaining_salvages(db) if include_inactive else list_retaining_salvages(db)

@lookup_router.post("/retaining_salvages", response_model=RetainingSalvageOut)
def create_retaining_salvage_router(payload: RetainingSalvageIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_retaining_salvage(db, data, actor_id(request))
    return RetainingSalvageOut.from_orm(obj)

@lookup_router.put("/retaining_salvages/{pk}", response_model=RetainingSalvageOut)
def update_retaining_salvage_router(pk: int, payload: RetainingSalvageIn, request: Request, db: Session = Depends(get_session)):
    obj = update_retaining_salvage(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return RetainingSalvageOut.from_orm(obj)

@lookup_router.patch("/retaining_salvages/{pk}/deactivate", response_model=RetainingSalvageOut)
def deactivate_retaining_salvage_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_retaining_salvage(db, pk, actor_id(request))
    return RetainingSalvageOut.from_orm(obj)

# ---------------- Policy_Type ------------------
@lookup_router.get("/policy_types", response_model=List[PolicyTypeOut])
def get_policy_type_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_policy_types(db) if include_inactive else list_policy_types(db)

@lookup_router.post("/policy_types", response_model=PolicyTypeOut)
def create_policy_type_router(payload: PolicyTypeIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_policy_type(db, data, actor_id(request))
    return PolicyTypeOut.from_orm(obj)

@lookup_router.put("/policy_types/{pk}", response_model=PolicyTypeOut)
def update_policy_type_router(pk: int, payload: PolicyTypeIn, request: Request, db: Session = Depends(get_session)):
    obj = update_policy_type(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return PolicyTypeOut.from_orm(obj)

@lookup_router.patch("/policy_types/{pk}/deactivate", response_model=PolicyTypeOut)
def deactivate_policy_type_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_policy_type(db, pk, actor_id(request))
    return PolicyTypeOut.from_orm(obj)

# ---------------- Cover Levels ------------------
@lookup_router.get("/cover_levels", response_model=List[CoverLevelOut])
def get_cover_level_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_cover_levels(db) if include_inactive else list_cover_levels(db)

@lookup_router.post("/cover_levels", response_model=CoverLevelOut)
def create_cover_level_router(payload: CoverLevelIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_cover_level(db, data, actor_id(request))
    return CoverLevelOut.from_orm(obj)

@lookup_router.put("/cover_levels/{pk}", response_model=CoverLevelOut)
def update_cover_level_router(pk: int, payload: CoverLevelIn, request: Request, db: Session = Depends(get_session)):
    obj = update_cover_level(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return CoverLevelOut.from_orm(obj)

@lookup_router.patch("/cover_levels/{pk}/deactivate", response_model=CoverLevelOut)
def deactivate_cover_level_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_cover_level(db, pk, actor_id(request))
    return CoverLevelOut.from_orm(obj)

# ---------------- Mid Reasons ------------------
@lookup_router.get("/mid_reasons", response_model=List[ReasonMidOut])
def get_mid_reason_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_mid_reasons(db) if include_inactive else list_mid_reasons(db)

@lookup_router.post("/mid_reasons", response_model=ReasonMidOut)
def create_mid_reason_router(payload: ReasonMidIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_mid_reason(db, data, actor_id(request))
    return ReasonMidOut.from_orm(obj)

@lookup_router.put("/mid_reasons/{pk}", response_model=ReasonMidOut)
def update_mid_reason_router(pk: int, payload: ReasonMidIn, request: Request, db: Session = Depends(get_session)):
    obj = update_mid_reason(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return ReasonMidOut.from_orm(obj)

@lookup_router.patch("/mid_reasons/{pk}/deactivate", response_model=ReasonMidOut)
def deactivate_mid_reason_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_mid_reason(db, pk, actor_id(request))
    return ReasonMidOut.from_orm(obj)

# ---------------- Liability Stance ------------------
@lookup_router.get("/liability_stances", response_model=List[LiabilityStanceOut])
def get_liability_stance_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_liability_stances(db) if include_inactive else list_liability_stances(db)

@lookup_router.post("/liability_stances", response_model=LiabilityStanceOut)
def create_liability_stance_router(payload: LiabilityStanceIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_liability_stance(db, data, actor_id(request))
    return LiabilityStanceOut.from_orm(obj)

@lookup_router.put("/liability_stances/{pk}", response_model=LiabilityStanceOut)
def update_liability_stance_router(pk: int, payload: LiabilityStanceIn, request: Request, db: Session = Depends(get_session)):
    obj = update_liability_stance(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return LiabilityStanceOut.from_orm(obj)

@lookup_router.patch("/liability_stances/{pk}/deactivate", response_model=LiabilityStanceOut)
def deactivate_liability_stance_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_liability_stance(db, pk, actor_id(request))
    return LiabilityStanceOut.from_orm(obj)

# ---------------- Settlement Status ------------------
@lookup_router.get("/settlement_statuses", response_model=List[SettlementStatusOut])
def get_settlement_status_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_settlement_statuses(db) if include_inactive else list_settlement_statuses(db)

@lookup_router.post("/settlement_statuses", response_model=SettlementStatusOut)
def create_settlement_status_router(payload: SettlementStatusIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_settlement_status(db, data, actor_id(request))
    return SettlementStatusOut.from_orm(obj)

# ---------------- Vehicle Status ------------------
@lookup_router.get("/vehicle_statuses", response_model=List[VehicleStatusOut])
def get_vehicle_status_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_vehicle_statuses(db) if include_inactive else list_vehicle_statuses(db)

@lookup_router.post("/vehicle_statuses", response_model=VehicleStatusOut)
def create_vehicle_status_router(payload: VehicleStatusIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_vehicle_status(db, data, actor_id(request))
    return VehicleStatusOut.from_orm(obj)

@lookup_router.put("/vehicle_statuses/{pk}", response_model=VehicleStatusOut)
def update_vehicle_status_router(pk: int, payload: VehicleStatusIn, request: Request, db: Session = Depends(get_session)):
    obj = update_vehicle_status(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return VehicleStatusOut.from_orm(obj)

@lookup_router.patch("/vehicle_statuses/{pk}/deactivate", response_model=VehicleStatusOut)
def deactivate_vehicle_status_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_vehicle_status(db, pk, actor_id(request))
    return VehicleStatusOut.from_orm(obj)

@lookup_router.put("/settlement_statuses/{pk}", response_model=SettlementStatusOut)
def update_settlement_status_router(pk: int, payload: SettlementStatusIn, request: Request, db: Session = Depends(get_session)):
    obj = update_settlement_status(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return SettlementStatusOut.from_orm(obj)

@lookup_router.patch("/settlement_statuses/{pk}/deactivate", response_model=SettlementStatusOut)
def deactivate_settlement_status_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_settlement_status(db, pk, actor_id(request))
    return SettlementStatusOut.from_orm(obj)

# ---------------- Client Vehicle Categories ------------------
@lookup_router.get("/client_vehicle_categories", response_model=List[ClientVehicleCategoryOut])
def get_client_vehicle_category_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_client_vehicle_categories(db) if include_inactive else list_client_vehicle_categories(db)

@lookup_router.post("/client_vehicle_categories", response_model=ClientVehicleCategoryOut)
def create_client_vehicle_category_router(payload: ClientVehicleCategoryIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_client_vehicle_category(db, data, actor_id(request))
    return ClientVehicleCategoryOut.from_orm(obj)

@lookup_router.put("/client_vehicle_categories/{pk}", response_model=ClientVehicleCategoryOut)
def update_client_vehicle_category_router(pk: int, payload: ClientVehicleCategoryIn, request: Request, db: Session = Depends(get_session)):
    obj = update_client_vehicle_category(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return ClientVehicleCategoryOut.from_orm(obj)

@lookup_router.patch("/client_vehicle_categories/{pk}/deactivate", response_model=ClientVehicleCategoryOut)
def deactivate_client_vehicle_category_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_client_vehicle_category(db, pk, actor_id(request))
    return ClientVehicleCategoryOut.from_orm(obj)

# ---------------- Actual Vehicle Categories ------------------
@lookup_router.get("/actual_vehicle_categories", response_model=List[ActualVehicleCategoryOut])
def get_actual_vehicle_category_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_actual_vehicle_categories(db) if include_inactive else list_actual_vehicle_categories(db)

@lookup_router.post("/actual_vehicle_categories", response_model=ActualVehicleCategoryOut)
def create_actual_vehicle_category_router(payload: ActualVehicleCategoryIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_actual_vehicle_category(db, data, actor_id(request))
    return ActualVehicleCategoryOut.from_orm(obj)

@lookup_router.put("/actual_vehicle_categories/{pk}", response_model=ActualVehicleCategoryOut)
def update_actual_vehicle_category_router(pk: int, payload: ActualVehicleCategoryIn, request: Request, db: Session = Depends(get_session)):
    obj = update_actual_vehicle_category(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return ActualVehicleCategoryOut.from_orm(obj)

@lookup_router.patch("/actual_vehicle_categories/{pk}/deactivate", response_model=ActualVehicleCategoryOut)
def deactivate_actual_vehicle_category_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_actual_vehicle_category(db, pk, actor_id(request))
    return ActualVehicleCategoryOut.from_orm(obj)

# ---------------- Admin Fee Types ------------------
@lookup_router.get("/admin_fee_types", response_model=List[AdminFeeTypeOut])
def get_admin_fee_type_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_admin_fee_types(db) if include_inactive else list_admin_fee_types(db)

@lookup_router.post("/admin_fee_types", response_model=AdminFeeTypeOut)
def create_admin_fee_type_router(payload: AdminFeeTypeIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_admin_fee_type(db, data, actor_id(request))
    return AdminFeeTypeOut.from_orm(obj)

@lookup_router.put("/admin_fee_types/{pk}", response_model=AdminFeeTypeOut)
def update_admin_fee_type_router(pk: int, payload: AdminFeeTypeIn, request: Request, db: Session = Depends(get_session)):
    obj = update_admin_fee_type(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return AdminFeeTypeOut.from_orm(obj)

@lookup_router.patch("/admin_fee_types/{pk}/deactivate", response_model=AdminFeeTypeOut)
def deactivate_admin_fee_type_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_admin_fee_type(db, pk, actor_id(request))
    return AdminFeeTypeOut.from_orm(obj)

# ---------------- Hire Vehicle Statuses ------------------
@lookup_router.get("/hire_vehicle_statuses", response_model=List[HireVehicleStatusOut])
def get_hire_vehicle_status_router(include_inactive: bool = False, db: Session = Depends(get_session)):
    return listall_hire_vehicle_statuses(db) if include_inactive else list_hire_vehicle_statuses(db)

@lookup_router.post("/hire_vehicle_statuses", response_model=HireVehicleStatusOut)
def create_hire_vehicle_status_router(payload: HireVehicleStatusIn, request: Request, db: Session = Depends(get_session)):
    data = payload.dict(exclude_unset=True)
    data["tenant_id"] = get_tenant_id(request)
    obj = create_hire_vehicle_status(db, data, actor_id(request))
    return HireVehicleStatusOut.from_orm(obj)

@lookup_router.put("/hire_vehicle_statuses/{pk}", response_model=HireVehicleStatusOut)
def update_hire_vehicle_status_router(pk: int, payload: HireVehicleStatusIn, request: Request, db: Session = Depends(get_session)):
    obj = update_hire_vehicle_status(db, pk, payload.dict(exclude_unset=True), actor_id(request))
    return HireVehicleStatusOut.from_orm(obj)

@lookup_router.patch("/hire_vehicle_statuses/{pk}/deactivate", response_model=HireVehicleStatusOut)
def deactivate_hire_vehicle_status_router(pk: int, request: Request, db: Session = Depends(get_session)):
    obj = deactivate_hire_vehicle_status(db, pk, actor_id(request))
    return HireVehicleStatusOut.from_orm(obj)
