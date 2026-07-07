from fastapi import APIRouter, Depends,File, UploadFile, Query,Form, Request
from sqlalchemy.orm import Session
from typing import List
from libdata.settings import get_session
from appflow.models.driver_check import DriverCheckBulkCreate, DriverCheckOut, DriverCheckBase, DriverCheckCreate
from appflow.services.driver_check_service import DriverCheckService
from appflow.utils import actor_id,get_tenant_id
import json

driver_check_router = APIRouter(prefix="/driver-checks", tags=["Driver Checks"])


@driver_check_router.post("/", response_model=List[DriverCheckOut])
def create_driver_check(payload: DriverCheckBulkCreate, db: Session = Depends(get_session),current_user=Depends(actor_id)):
    return DriverCheckService.create_driver_checks(payload, db,current_user)

@driver_check_router.get("/claim/{claim_id}", response_model=List[DriverCheckOut])
def get_driver_checks_by_claim(request: Request, claim_id: int, db: Session = Depends(get_session)):
    return DriverCheckService.get_driver_checks_by_claim(claim_id, db, request=request)

@driver_check_router.put("/deactivate/{hire_vehicle_provided_id}")
def deactivate_hire_vehicle(hire_vehicle_provided_id: int, db: Session = Depends(get_session)):
    return DriverCheckService.deactivate_hire_vehicle(hire_vehicle_provided_id, db)

@driver_check_router.put("/deactivate/{claim_id}")
def deactivate_driver_checks_by_claim(claim_id: int, db: Session = Depends(get_session)):
    return DriverCheckService.deactivate_driver_checks_by_claim(claim_id, db)

@driver_check_router.put("/hire-vehicle/{hire_vehicle_provided_id}", response_model=DriverCheckOut)
def update_driver_check_by_hire_vehicle(
    hire_vehicle_provided_id: int,payload: DriverCheckBase,db: Session = Depends(get_session),current_user=Depends(actor_id)):
    return DriverCheckService.update_driver_check_by_hire_vehicle(hire_vehicle_provided_id, payload, db, current_user)

@driver_check_router.get("/hire-vehicle/{hire_vehicle_provided_id}", response_model=DriverCheckOut)
def get_driver_check_by_hire_vehicle(
    request: Request,
    hire_vehicle_provided_id: int,
    db: Session = Depends(get_session)
):
    return DriverCheckService.get_driver_check_by_hire_vehicle(hire_vehicle_provided_id, db,request=request)

@driver_check_router.post("/{driver_check_id}/images", response_model=List[str])
def upload_driver_check_images(
    driver_check_id: int,
    image_type: str = Query(..., description="interior or exterior"),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_session),
    current_user=Depends(actor_id)
):
    created = DriverCheckService.save_driver_check_images(driver_check_id, image_type, files, db, current_user)
    # return list of saved file paths
    return [c.file_path for c in created]

@driver_check_router.get("/{driver_check_id}/images", response_model=List[str])
def list_driver_check_images(router_driver_check_id: int, db: Session = Depends(get_session)):
    imgs = DriverCheckService.list_driver_check_images(router_driver_check_id, db)
    return [i.file_path for i in imgs]

@driver_check_router.delete("/images/{image_id}")
def delete_driver_check_image(image_id: int, db: Session = Depends(get_session), current_user=Depends(actor_id)):
    return DriverCheckService.delete_driver_check_image(image_id, db)


@driver_check_router.post("/save-checkout", response_model=DriverCheckOut)
async def save_checkout(
    request: Request,
    currency: str = Form(...),
    interior_clean_at_check_out: bool = Form(...),
    interior_clean_at_check_in: bool = Form(...),
    interior_damage_at_check_in: bool = Form(...),
    describe_interior_damage: str = Form(None),

    exterior_clean_at_check_out: bool = Form(...),
    exterior_clean_at_check_in: bool = Form(...),
    exterior_damage_at_check_in: bool = Form(...),
    describe_exterior_damage: str = Form(None),

    apply_petrol_checkout_charges: bool = Form(...),
    petrol_checkout_charges: float = Form(None),
    petrol_charges_note: str = Form(None),

    apply_damage_charges: bool = Form(...),
    damage_charges: float = Form(None),
    damage_charges_paid_now: float = Form(None),
    damage_charges_note: str = Form(None),
    damage_charges_paid: bool = Form(False),

    valet_charges: float = Form(None),
    total_driver_checkout_charges: float = Form(None),

    claim_id: int = Form(...),
    hire_vehicle_provided_id: int = Form(...),

    interior_files: List[UploadFile] = File(None),
    exterior_files: List[UploadFile] = File(None),

    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
    tenant_id=Depends(get_tenant_id),
):
    """Create or update a driver checkout record, with optional interior/exterior photos."""
    data = {
        "currency": currency,
        "interior_clean_at_check_out": interior_clean_at_check_out,
        "interior_clean_at_check_in": interior_clean_at_check_in,
        "interior_damage_at_check_in": interior_damage_at_check_in,
        "describe_interior_damage": describe_interior_damage,
        "exterior_clean_at_check_out": exterior_clean_at_check_out,
        "exterior_clean_at_check_in": exterior_clean_at_check_in,
        "exterior_damage_at_check_in": exterior_damage_at_check_in,
        "describe_exterior_damage": describe_exterior_damage,
        "apply_petrol_checkout_charges": apply_petrol_checkout_charges,
        "petrol_checkout_charges": petrol_checkout_charges,
        "petrol_charges_note": petrol_charges_note,
        "apply_damage_charges": apply_damage_charges,
        "damage_charges": damage_charges,
        "damage_charges_paid_now": damage_charges_paid_now,
        "damage_charges_note": damage_charges_note,
        "damage_charges_paid": damage_charges_paid,
        "valet_charges": valet_charges,
        "total_driver_checkout_charges": total_driver_checkout_charges,
        "claim_id": claim_id,
        "hire_vehicle_provided_id": hire_vehicle_provided_id,
    }
    payload = DriverCheckCreate(**data)
    return DriverCheckService.save_checkout_json(
        payload, db, current_user, tenant_id, interior_files, exterior_files
    )


@driver_check_router.post("/hire-vehicle/{hire_vehicle_provided_id}/checkout-email")
def send_checkout_email(
    hire_vehicle_provided_id: int,
    claim_id: int,
    db: Session = Depends(get_session),
):
    return DriverCheckService.send_checkout_email(claim_id, hire_vehicle_provided_id, db)

@driver_check_router.post("/single", response_model=DriverCheckOut)
async def create_single_driver_check(
    request:Request,
    currency: str = Form(...),
    interior_clean_at_check_out: bool = Form(...),
    interior_clean_at_check_in: bool = Form(...),
    interior_damage_at_check_in: bool = Form(...),
    describe_interior_damage: str = Form(None),

    exterior_clean_at_check_out: bool = Form(...),
    exterior_clean_at_check_in: bool = Form(...),
    exterior_damage_at_check_in: bool = Form(...),
    describe_exterior_damage: str = Form(None),

    apply_petrol_checkout_charges: bool = Form(...),
    petrol_checkout_charges: float = Form(None),
    petrol_charges_note: str = Form(None),

    apply_damage_charges: bool = Form(...),
    damage_charges: float = Form(None),
    damage_charges_paid_now: float = Form(None),
    damage_charges_note: str = Form(None),
    damage_charges_paid: bool = Form(...),

    valet_charges: float = Form(None),
    total_driver_checkout_charges: float = Form(None),

    claim_id: int = Form(...),
    hire_vehicle_provided_id: int = Form(...),

    interior_files: List[UploadFile] = File(None),
    exterior_files: List[UploadFile] = File(None),

    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
    tenant_id=Depends(get_tenant_id)
):
    data = {
        "currency": currency,
        "interior_clean_at_check_out": interior_clean_at_check_out,
        "interior_clean_at_check_in": interior_clean_at_check_in,
        "interior_damage_at_check_in": interior_damage_at_check_in,
        "describe_interior_damage": describe_interior_damage,
        "exterior_clean_at_check_out": exterior_clean_at_check_out,
        "exterior_clean_at_check_in": exterior_clean_at_check_in,
        "exterior_damage_at_check_in": exterior_damage_at_check_in,
        "describe_exterior_damage": describe_exterior_damage,
        "apply_petrol_checkout_charges": apply_petrol_checkout_charges,
        "petrol_checkout_charges": petrol_checkout_charges,
        "petrol_charges_note": petrol_charges_note,
        "apply_damage_charges": apply_damage_charges,
        "damage_charges": damage_charges,
        "damage_charges_paid_now": damage_charges_paid_now,
        "damage_charges_note": damage_charges_note,
        "damage_charges_paid": damage_charges_paid,
        "valet_charges": valet_charges,
        "total_driver_checkout_charges": total_driver_checkout_charges,
        "claim_id": claim_id,
        "hire_vehicle_provided_id": hire_vehicle_provided_id,
    }

    payload = DriverCheckCreate(**data)

    return DriverCheckService.create_single_driver_check(
        payload, db, current_user,tenant_id, interior_files, exterior_files,request=request
    )

@driver_check_router.put("/update-by-hire-vehicle-image", response_model=DriverCheckOut)
async def update_driver_check_by_hire_vehicle_image(
    request: Request,
    claim_id: int = Form(...),
    hire_vehicle_provided_id: int = Form(...),
    currency: str = Form(...),
    interior_clean_at_check_out: bool = Form(...),
    interior_clean_at_check_in: bool = Form(...),
    interior_damage_at_check_in: bool = Form(...),
    describe_interior_damage: str = Form(None),

    exterior_clean_at_check_out: bool = Form(...),
    exterior_clean_at_check_in: bool = Form(...),
    exterior_damage_at_check_in: bool = Form(...),
    describe_exterior_damage: str = Form(None),

    apply_petrol_checkout_charges: bool = Form(...),
    petrol_checkout_charges: float = Form(None),
    petrol_charges_note: str = Form(None),

    apply_damage_charges: bool = Form(...),
    damage_charges: float = Form(None),
    damage_charges_paid_now: float = Form(None),
    damage_charges_note: str = Form(None),
    damage_charges_paid: bool = Form(...),

    valet_charges: float = Form(None),
    total_driver_checkout_charges: float = Form(None),

    interior_files: List[UploadFile] = File(None),
    exterior_files: List[UploadFile] = File(None),

    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
    tenant_id = Depends(get_tenant_id)
):
    data = {
        "currency": currency,
        "interior_clean_at_check_out": interior_clean_at_check_out,
        "interior_clean_at_check_in": interior_clean_at_check_in,
        "interior_damage_at_check_in": interior_damage_at_check_in,
        "describe_interior_damage": describe_interior_damage,
        "exterior_clean_at_check_out": exterior_clean_at_check_out,
        "exterior_clean_at_check_in": exterior_clean_at_check_in,
        "exterior_damage_at_check_in": exterior_damage_at_check_in,
        "describe_exterior_damage": describe_exterior_damage,
        "apply_petrol_checkout_charges": apply_petrol_checkout_charges,
        "petrol_checkout_charges": petrol_checkout_charges,
        "petrol_charges_note": petrol_charges_note,
        "apply_damage_charges": apply_damage_charges,
        "damage_charges": damage_charges,
        "damage_charges_paid_now": damage_charges_paid_now,
        "damage_charges_note": damage_charges_note,
        "damage_charges_paid": damage_charges_paid,
        "valet_charges": valet_charges,
        "total_driver_checkout_charges": total_driver_checkout_charges,
        "claim_id": claim_id,
        "hire_vehicle_provided_id": hire_vehicle_provided_id,
    }

    payload = DriverCheckCreate(**data)

    return DriverCheckService.update_driver_check_by_hire_vehicle_image(
        hire_vehicle_provided_id=hire_vehicle_provided_id,
        payload=payload,
        db=db,
        current_user=current_user,
        tenant_id=tenant_id,
        interior_files=interior_files,
        exterior_files=exterior_files,
        request=request
    )
