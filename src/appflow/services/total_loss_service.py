from sqlalchemy.orm import Session
from fastapi import HTTPException
from libdata.models.tables import TotalLoss
from appflow.models.total_loss import TotalLossIn
from appflow.utils import get_tenant_id,actor_id,build_case_reference
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType

def create_total_loss(db: Session, total_loss_in: TotalLossIn, request):
    current_user_id = actor_id(request)
    tenant_id = get_tenant_id(request)
    total_loss = TotalLoss(**total_loss_in.dict(), is_active=True)
    total_loss.created_by = current_user_id
    total_loss.updated_by = current_user_id
    db.add(total_loss)
    db.commit()
    db.refresh(total_loss)
    reference = build_case_reference(total_loss.claim_id,db)
    HistoryActivityService.create_activity(
        db=db,
        claim_id=total_loss.claim_id,
        file_name=f"The total loss detail has been created for claim {reference}",
        file_path="",
        file_type=HistoryLogType.CREATED_LOSS_DETAIL,
        user_id=current_user_id,
        tenant_id=tenant_id
    )
    return total_loss


def get_total_loss_by_claim(db: Session, claim_id: int):
    total_loss = db.query(TotalLoss).filter(
        TotalLoss.claim_id == claim_id,
        TotalLoss.is_active == True
    ).first()
    if not total_loss:
        raise HTTPException(status_code=404, detail="Total Loss record not found")
    return total_loss


def update_total_loss_by_claim(db: Session, claim_id: int, total_loss_in: TotalLossIn, request):
    current_user_id = actor_id(request)
    tenant_id = get_tenant_id(request)
    total_loss = db.query(TotalLoss).filter(
        TotalLoss.claim_id == claim_id,
        TotalLoss.is_active == True
    ).first()
    if not total_loss:
        raise HTTPException(status_code=404, detail="Total Loss record not found")

    changed_fields = []

    # Map field names to readable labels
    field_label_map = {
        "currency": "Currency",
        "total_loss_date": "Total Loss Date",
        "pav": "PAV",
        "salvage_amount": "Salvage Amount",
        "salvage_category_id": "Salvage Category",
        "keeping_salvage_id": "Keeping Salvage",
        "pav_agreed_id": "PAV Agreed",
        "retaining_salvage_id": "Retaining Salvage",
        "engineer_report_sent_tpi": "Engineer Report Sent TPI",
        "pav_cheque_received": "PAV Cheque Received",
        "pav_sent_client": "PAV Sent Client",
        "vehicle_salvage_milage": "Vehicle Salvage Milage",
        "pav_offer_made_client": "PAV Offer Made Client",
        "pav_offer_accepted": "PAV Offer Accepted",
        "tpi_instructed_collect_saving_on": "TPI Instructed Collect Saving On",
        "has_salvage_been_collected": "Has Salvage Been Collected",
        "salvage_collect_on": "Salvage Collect On",
    }

    # Track changes
    for field, new_value in total_loss_in.dict(exclude_unset=True).items():
        old_value = getattr(total_loss, field)
        if old_value != new_value:
            changed_fields.append(field_label_map.get(field, field))
            setattr(total_loss, field, new_value)
    total_loss.updated_by = current_user_id
    db.commit()
    db.refresh(total_loss)
    if changed_fields:
        file_path = ", ".join(changed_fields)
        reference = build_case_reference(claim_id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=claim_id,
            file_name=f"The total loss has been updated for claim {reference}",
            file_path=file_path,
            file_type=HistoryLogType.UPDATED_LOSS_DETAIL,
            user_id=current_user_id,
            tenant_id=tenant_id
        )
    return total_loss


def deactivate_total_loss_by_claim(db: Session, claim_id: int):
    total_loss = db.query(TotalLoss).filter(
        TotalLoss.claim_id == claim_id,
        TotalLoss.is_active == True
    ).first()
    if not total_loss:
        raise HTTPException(status_code=404, detail="Total Loss record not found")

    total_loss.is_active = False
    db.commit()
    return {"message": "Total Loss deactivated successfully"}
