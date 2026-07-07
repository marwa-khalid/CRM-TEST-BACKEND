from sqlalchemy.orm import Session
from libdata.models.tables import DirectHirePayment
from appflow.models.direct_hire_payment import DirectHirePaymentIn


class DirectHirePaymentService:

    @staticmethod
    def get_by_claim(claim_id: int, db: Session):
        return (
            db.query(DirectHirePayment)
            .filter(
                DirectHirePayment.claim_id == claim_id,
                DirectHirePayment.is_active == True,
                DirectHirePayment.is_deleted == False,
            )
            .first()
        )

    @staticmethod
    def save(payload: DirectHirePaymentIn, db: Session, current_user: int):
        existing = DirectHirePaymentService.get_by_claim(payload.claim_id, db)
        if existing:
            for k, v in payload.model_dump(exclude={"claim_id"}).items():
                setattr(existing, k, v)
            existing.updated_by = current_user
            db.commit()
            db.refresh(existing)
            return existing
        record = DirectHirePayment(
            **payload.model_dump(),
            created_by=current_user,
            updated_by=current_user,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
