from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from libdata.models.tables import RouteRepair
from appflow.models.route_repair import RouteRepairCreate, RouteRepairOut
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType
from appflow.utils import get_tenant_id,actor_id,build_case_reference

def create_route_repair(db: Session, route_repair_in: RouteRepairCreate,request) -> RouteRepair:
    tenant_id = get_tenant_id(request)
    current_user_id = actor_id(request)
    db_obj = RouteRepair(**route_repair_in.dict())
    db_obj.created_by = current_user_id
    db_obj.updated_by = current_user_id
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    reference = build_case_reference(db_obj.claim_id,db)
    HistoryActivityService.create_activity(
        db=db,
        claim_id=db_obj.claim_id,
        file_name=f"The repair costs & route details has been created for claim {reference}",
        file_path="",
        file_type=HistoryLogType.CREATED_REPAIR_DETAIL,
        user_id=current_user_id,
        tenant_id=tenant_id
    )
    return db_obj


def get_route_repairs_by_claim(db: Session, claim_id: int):
    repair_cost = db.query(RouteRepair).filter(
        RouteRepair.claim_id == claim_id,
        RouteRepair.is_active == True
    ).first()
    if not repair_cost:
        raise HTTPException(status_code=404, detail="Repair Cost record not found")
    return repair_cost


def update_route_repair_by_claim(db: Session, claim_id: int, route_repair_in: RouteRepairCreate,request) -> RouteRepair:
    tenant_id = get_tenant_id(request)
    current_user_id = actor_id(request)
    db_obj = db.query(RouteRepair).filter(RouteRepair.claim_id == claim_id, RouteRepair.is_active == True).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail=f"No active RouteRepair found for claim {claim_id}")

    update_data = route_repair_in.dict(exclude_unset=True)
    changed_fields = []

    # Track changes and update
    for field, new_value in update_data.items():
        old_value = getattr(db_obj, field)
        if new_value != old_value:
            changed_fields.append(field)  # Track field name only
            setattr(db_obj, field, new_value)
    db_obj.updated_by = current_user_id
    db.commit()
    db.refresh(db_obj)
    reference = build_case_reference(claim_id,db)
    # Record history activity only if anything changed
    if changed_fields:
        # Optional: make fields more readable (example mapping)
        field_label_map = {
            "currency": "Currency",
            "labour": "Labour",
            "paint_material": "Paint Material",
            "parts": "Parts",
            "miscellaneous": "Miscellaneous",
            "job_hire": "Job Hire",
            "sub_total": "Sub Total",
            "vat": "VAT",
            "total_inc_vat": "Total Including VAT",
            "cil_total_received": "CIL Total Received",
            "actual_repair_costs_parts": "Actual Repair Costs (Parts)",
            "actual_repair_costs_labour": "Actual Repair Costs (Labour)",
            "net_cil_amount": "Net CIL Amount",
            "cil_agreed": "CIL Agreed",
            "if_roadworthy_cil_fee_agreed": "If Roadworthy CIL Fee Agreed",
            "agreement_received": "Agreement Received",
            "eng_rep_sent_tpi": "Engineer Report Sent to TPI",
            "cil_cheque_request": "CIL Cheque Request",
            "cil_cheque_sent_cl": "CIL Cheque Sent to Client",
            "cil_removal_confirmation_received": "CIL Removal Confirmation Received",
            "repair_est_days": "Repair Estimated Days",
            "repair_inst": "Repair Instruction Date",
            "repair_auth": "Repair Authorization Date",
            "estimated_received": "Estimated Received Date",
            "repair_start": "Repair Start Date",
            "repair_completed": "Repair Completed Date",
        }
        readable_changes = [field_label_map.get(f, f) for f in changed_fields]
        HistoryActivityService.create_activity(
            db=db,
            claim_id=claim_id,
            file_name=f"The repair costs & route details has been updated for claim {reference}",
            file_path=", ".join(readable_changes),
            file_type=HistoryLogType.UPDATED_REPAIR_DETAIL,
            user_id=current_user_id,
            tenant_id=tenant_id
        )
    return db_obj


def deactivate_route_repair(db: Session, route_repair_id: int) -> dict:
    db_obj = db.query(RouteRepair).filter(RouteRepair.id == route_repair_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail=f"RouteRepair with id {route_repair_id} not found")

    db_obj.is_active = False
    db.commit()
    return {"detail": f"RouteRepair {route_repair_id} deactivated"}
