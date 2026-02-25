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
)
from appflow.services.lookups_service import (
    # list (active only)
    list_claim_types, list_handlers, list_target_debts, list_case_statuses,
    list_source_channels, list_prospects, list_present_positions, list_languages,list_fuel_types,list_transmissions,list_taxi_types,
    # list all (admin view)
    listall_claim_types, listall_handlers, listall_target_debts, listall_case_statuses,
    listall_source_channels, listall_prospects, listall_present_positions, listall_languages,listall_fuel_types,listall_transmissions,listall_taxi_types,
    # CRUD
    create_claim_type, update_claim_type, deactivate_claim_type,
    create_handler, update_handler, deactivate_handler,
    create_target_debt, update_target_debt, deactivate_target_debt,
    create_case_status, update_case_status, deactivate_case_status,
    create_source_channel, update_source_channel, deactivate_source_channel,
    create_prospect, update_prospect, deactivate_prospect,
    create_present_position, update_present_position, deactivate_present_position, create_language, update_language,
    deactivate_language,create_fuel_type,update_fuel_type,deactivate_fuel_type,
    create_transmission,update_transmission,deactivate_transmission,create_taxi_type,update_taxi_type,deactivate_taxi_type
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
    return listall_fuel_types(db) if include_inactive else list_taxi_types(db)

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