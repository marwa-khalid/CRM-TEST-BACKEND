from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import Optional

from libdata.models.tables import PlatingAdditionalCharges
from appflow.models.plating_charges import PlatingChargesIn, PlatingChargesOut


class PlatingChargesService:

    @staticmethod
    def get_by_claim(claim_id: int, db: Session, vehicle_id: Optional[int] = None) -> Optional[PlatingChargesOut]:
        q = (
            db.query(PlatingAdditionalCharges)
            .filter(
                PlatingAdditionalCharges.claim_id == claim_id,
                PlatingAdditionalCharges.is_active == True,
                PlatingAdditionalCharges.is_deleted == False,
            )
        )
        # Plating is per vehicle; a null vehicle_id matches the legacy per-claim row.
        if vehicle_id is not None:
            q = q.filter(PlatingAdditionalCharges.client_vehicle_id == vehicle_id)
        else:
            q = q.filter(PlatingAdditionalCharges.client_vehicle_id.is_(None))
        return q.first()

    @staticmethod
    def get_total(claim_id: int, db: Session) -> float:
        """Sum of total_plating_cost across all of a claim's (per-vehicle) rows."""
        rows = (
            db.query(PlatingAdditionalCharges)
            .filter(
                PlatingAdditionalCharges.claim_id == claim_id,
                PlatingAdditionalCharges.is_active == True,
                PlatingAdditionalCharges.is_deleted == False,
            )
            .all()
        )
        return float(sum((r.total_plating_cost or 0) for r in rows))

    @staticmethod
    def save(payload: PlatingChargesIn, db: Session, current_user: int) -> PlatingChargesOut:
        existing = PlatingChargesService.get_by_claim(
            payload.claim_id, db, payload.client_vehicle_id
        )

        fields = {
            "private_hire_plating_fee": payload.private_hire_plating_fee,
            "private_hire_mot_cost": payload.private_hire_mot_cost,
            "total_plating_cost": payload.total_plating_cost,
            "automatic": payload.automatic,
            "estate": payload.estate,
            "additional_premium": payload.additional_premium,
            "additional_driver_charges": payload.additional_driver_charges,
        }

        try:
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                existing.updated_by = current_user
                db.commit()
                db.refresh(existing)
                return existing
            else:
                row = PlatingAdditionalCharges(
                    claim_id=payload.claim_id,
                    client_vehicle_id=payload.client_vehicle_id,
                    created_by=current_user,
                    updated_by=current_user,
                    **fields,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return row
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error saving plating charges: {str(e)}")
