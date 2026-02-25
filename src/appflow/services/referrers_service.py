from sqlalchemy.orm import Session,joinedload
from fastapi import HTTPException
from libdata.models.tables import Referrer, ReferrerCommission, DriverCommission,Company
from appflow.models.referrers import ReferrerCommissionCreate,DriverCommissionCreate,ReferrerCreate,ReferrerResponse
from libdata.models.tables import Claim


class ReferrerService:

    @staticmethod
    def get_referrer_by_claim_id(claim_id: int, db: Session):
        existing = db.query(Referrer).filter(Referrer.claim_id == claim_id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Referrer not found")
        return existing

    @staticmethod
    def get_referrer_by_company_name(company_name: str, db: Session):
        existing = db.query(Referrer).filter(Referrer.company_name == company_name).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Referrer not found")
        return existing

    @staticmethod
    def create_referrer(referrer: ReferrerCreate, db: Session, tenant_id: int):
        # Check if company already exists for this tenant
        # if db.query(Referrer).filter(
        #         Referrer.company_name == referrer.company_name,
        #         Referrer.tenant_id == tenant_id
        # ).first():
        #     raise HTTPException(status_code=400, detail="Company already exists")

        # Check if claim exists
        claim = db.query(Claim).filter(
            Claim.id == referrer.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        try:
            # Create DriverCommission
            driver_commission = None
            if referrer.driver_commission:
                print("Loading")
                driver_commission_data = referrer.driver_commission.dict()
                driver_commission = DriverCommission(
                    **driver_commission_data,
                    tenant_id=tenant_id
                )
                db.add(driver_commission)
                db.flush()

            # Create ReferrerCommission
            referrer_commission = None
            if referrer.referrer_commission:
                print("Loading")
                referrer_commission_data = referrer.referrer_commission.dict()
                referrer_commission = ReferrerCommission(
                    **referrer_commission_data,
                    tenant_id=tenant_id
                )
                db.add(referrer_commission)
                db.flush()

            # Create Referrer with commission IDs
            referrer_data = referrer.dict(exclude={'driver_commission', 'referrer_commission'})
            new_referrer = Referrer(
                **referrer_data,
                tenant_id=tenant_id,
                driver_commission_id=driver_commission.id,
                referrer_commission_id=referrer_commission.id
            )

            db.add(new_referrer)
            db.commit()
            db.refresh(new_referrer)

            # Eager load the relationships
            new_referrer = db.query(Referrer).options(
                joinedload(Referrer.driver_commission),
                joinedload(Referrer.referrer_commission)
            ).filter(Referrer.id == new_referrer.id).first()

            return new_referrer

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creating referrer: {str(e)}")

    @staticmethod
    def update_referrer(claim_id: int, referrer: ReferrerCreate, db: Session, tenant_id: int):
        existing = db.query(Referrer).filter(
            Referrer.claim_id == claim_id,
            Referrer.tenant_id == tenant_id
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Referrer not found")

        # Check if claim exists
        claim = db.query(Claim).filter(
            Claim.id == referrer.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        try:
            # Update DriverCommission
            driver_commission_data = referrer.driver_commission.dict(exclude_unset=True)
            for key, value in driver_commission_data.items():
                setattr(existing.driver_commission, key, value)

            # Update ReferrerCommission
            referrer_commission_data = referrer.referrer_commission.dict(exclude_unset=True)
            for key, value in referrer_commission_data.items():
                setattr(existing.referrer_commission, key, value)

            # Update Referrer fields
            referrer_data = referrer.dict(exclude={'driver_commission', 'referrer_commission'}, exclude_unset=True)
            for key, value in referrer_data.items():
                setattr(existing, key, value)

            db.commit()
            db.refresh(existing)

            # Eager load the relationships
            existing = db.query(Referrer).options(
                joinedload(Referrer.driver_commission),
                joinedload(Referrer.referrer_commission)
            ).filter(Referrer.id == existing.id).first()

            return existing

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error updating referrer: {str(e)}")

    @staticmethod
    def delete_referrer(referrer_id: int, db: Session, tenant_id: int):
        referrer_to_delete = db.query(Referrer).filter(
            Referrer.id == referrer_id,
            Referrer.tenant_id == tenant_id
        ).first()

        if not referrer_to_delete:
            raise HTTPException(status_code=404, detail="Referrer not found")

        try:
            # Get commission IDs before deletion
            driver_commission_id = referrer_to_delete.driver_commission_id
            referrer_commission_id = referrer_to_delete.referrer_commission_id

            # Delete the referrer
            db.delete(referrer_to_delete)

            # Delete associated commissions
            db.query(DriverCommission).filter(DriverCommission.id == driver_commission_id).delete()
            db.query(ReferrerCommission).filter(ReferrerCommission.id == referrer_commission_id).delete()

            db.commit()
            return {"detail": "Referrer and associated commissions deleted successfully"}

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error deleting referrer: {str(e)}")

    # @staticmethod
    # def search_referrers(query: str, db: Session, tenant_id: int):
    #     return db.query(Referrer).options(
    #         joinedload(Referrer.driver_commission),
    #         joinedload(Referrer.referrer_commission)
    #     ).filter(
    #         Referrer.company_name.ilike(f"%{query}%"),
    #     ).all()
    @staticmethod
    def search_referrers(query: str, db: Session, tenant_id: int):
        return (
            db.query(Referrer)
            .filter(
                Referrer.company_name.ilike(f"%{query.strip()}%")
            )
            .all()
        )
    
    @staticmethod
    def search_companies(query: str, db: Session):
        return (
            db.query(Company)
            .filter(
                Company.company_name.ilike(f"%{query.strip()}%")
            )
            .all()
        )

