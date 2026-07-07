from sqlalchemy.orm import Session,joinedload
from fastapi import HTTPException
from libdata.models.tables import Referrer, ReferrerCommission, DriverCommission,Company
from appflow.models.referrers import ReferrerCommissionCreate,DriverCommissionCreate,ReferrerCreate,ReferrerResponse,ReferrerDisplayLabels
from libdata.models.tables import Claim
from libdata.enums import HistoryLogType
from appflow.services.history_activity_service import HistoryActivityService
from appflow.utils import build_case_reference
from datetime import datetime

class ReferrerService:

    @staticmethod
    def _upsert_company(db: Session, company_name, address=None, postcode=None):
        """Persist a typed company into the global `companies` lookup so it can
        be reused on other claims / by other users. If the company already
        exists, fill in / update its address & postcode from what the user
        entered, so next time this company is picked its address auto-fills.
        Committed on its own so the lookup survives regardless of the referrer
        save outcome."""
        name = (company_name or "").strip()
        if not name:
            return
        addr = (address or "").strip() or None
        pc = (postcode or "").strip() or None
        try:
            existing = (
                db.query(Company).filter(Company.company_name.ilike(name)).first()
            )
            if existing:
                changed = False
                # Fill blanks, and update when the user provided a newer value.
                if addr and addr != existing.address:
                    existing.address = addr
                    changed = True
                if pc and pc != existing.postcode:
                    existing.postcode = pc
                    changed = True
                if changed:
                    db.commit()
                return
            db.add(Company(company_name=name, address=addr, postcode=pc))
            db.commit()
        except Exception:
            db.rollback()

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
    def create_referrer(referrer: ReferrerCreate, db: Session, tenant_id: int,actor_id: int):
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

        # Save any new company name into the reusable global lookup.
        ReferrerService._upsert_company(db, referrer.company_name,
                                        getattr(referrer, "address", None),
                                        getattr(referrer, "postcode", None))

        try:
            driver_commission = None
            if referrer.driver_commission:
                driver_commission_data = referrer.driver_commission.dict(exclude_unset=True)
                driver_commission = DriverCommission(**driver_commission_data, tenant_id=tenant_id)
                driver_commission.created_by=actor_id
                driver_commission.updated_by=actor_id
                db.add(driver_commission)
                db.flush()

            referrer_commission = None
            if referrer.referrer_commission:
                referrer_commission_data = referrer.referrer_commission.dict(exclude_unset=True)
                referrer_commission = ReferrerCommission(**referrer_commission_data, tenant_id=tenant_id)
                referrer_commission.created_by=actor_id
                referrer_commission.updated_by=actor_id
                db.add(referrer_commission)
                db.flush()

            # Create Referrer with commission IDs
            referrer_data = referrer.dict(exclude={'driver_commission', 'referrer_commission'})
            new_referrer = Referrer(
                **referrer_data,
                tenant_id=tenant_id,
                driver_commission_id=driver_commission.id if driver_commission else None,
                referrer_commission_id=referrer_commission.id if referrer_commission else None,
                created_by = actor_id,
                updated_by = actor_id
            )

            db.add(new_referrer)
            db.commit()
            db.refresh(new_referrer)
            # reference = build_case_reference(claim.id,db)
            current_yyyymm = datetime.now().strftime("%Y%m")
            padded_claim_id = str(claim.id).zfill(5)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim.id,
                file_name=f"The referrer has been created for claim-{current_yyyymm}-{padded_claim_id}",
                file_path="",
                file_type=HistoryLogType.CREATED_REFERRER_DETAIL,
                user_id=actor_id,
                tenant_id=tenant_id
            )
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
    def update_referrer(claim_id: int, referrer: ReferrerCreate, db: Session, tenant_id: int, actor_id: int):
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

        # Save any new company name into the reusable global lookup.
        ReferrerService._upsert_company(db, referrer.company_name,
                                        getattr(referrer, "address", None),
                                        getattr(referrer, "postcode", None))

        changed_labels = []
        try:
            # Handle Driver Commission
            driver_data = referrer.driver_commission.dict(exclude_unset=True)
            for k, v in driver_data.items():
                old = getattr(existing.driver_commission, k)
                if old != v:
                    setattr(existing.driver_commission, k, v)
                    changed_labels.append(ReferrerDisplayLabels.format(k))

            # Handle Referrer Commission
            referrer_data = referrer.referrer_commission.dict(exclude_unset=True)
            for k, v in referrer_data.items():
                old = getattr(existing.referrer_commission, k)
                if old != v:
                    setattr(existing.referrer_commission, k, v)
                    changed_labels.append(ReferrerDisplayLabels.format(f"ref_{k}"))

            # Parent Referrer fields
            parent_data = referrer.dict(exclude={'driver_commission', 'referrer_commission'}, exclude_unset=True)
            for k, v in parent_data.items():
                if v is None:
                    continue
                old = getattr(existing, k)
                if old != v:
                    setattr(existing, k, v)
                    changed_labels.append(ReferrerDisplayLabels.format(k))

            # If no changes were made, return early without creating activity
            if not changed_labels:
                # Eager load the relationships and return existing data
                existing = db.query(Referrer).options(
                    joinedload(Referrer.driver_commission),
                    joinedload(Referrer.referrer_commission)
                ).filter(Referrer.id == existing.id).first()
                return existing

            db.commit()
            db.refresh(existing)
            reference = build_case_reference(claim.id, db)

            # Now file_path will always be defined since we're inside the if block
            file_path = ", ".join(changed_labels)
            current_yyyymm = datetime.now().strftime("%Y%m")
            padded_claim_id = str(claim.id).zfill(5)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim.id,
                file_name=f"The referrer details has been updated for claim-{current_yyyymm}-{padded_claim_id}",
                file_path=file_path,
                file_type=HistoryLogType.UPDATED_REFERRER_DETAIL,
                user_id=actor_id,
                tenant_id=tenant_id
            )

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
    
    @staticmethod
    def search_companies(query: str, db: Session, tenant_id: int):
        search = (query or "").strip()
        if not search:
            return []

        results = []
        seen = set()

        def add_company(company_name, address=None, postcode=None):
            name = (company_name or "").strip()
            key = name.lower()
            if not name or key in seen:
                return
            seen.add(key)
            results.append({
                "company_name": name,
                "address": address,
                "postcode": postcode,
            })

        companies = (
            db.query(Company)
            .filter(Company.company_name.ilike(f"%{search}%"))
            .order_by(Company.company_name.asc())
            .limit(20)
            .all()
        )
        for company in companies:
            add_company(company.company_name, company.address, company.postcode)

        referrers = (
            db.query(Referrer.company_name, Referrer.address, Referrer.postcode)
            .filter(
                Referrer.tenant_id == tenant_id,
                Referrer.company_name.ilike(f"%{search}%"),
            )
            .order_by(Referrer.company_name.asc())
            .limit(20)
            .all()
        )
        for company_name, address, postcode in referrers:
            add_company(company_name, address, postcode)

        return results[:20]

    @staticmethod
    def search_referrers(query: str, db: Session, tenant_id: int):
        return db.query(Referrer).options(
            joinedload(Referrer.driver_commission),
            joinedload(Referrer.referrer_commission)
        ).filter(
            Referrer.company_name.ilike(f"%{query}%"),
            Referrer.tenant_id == tenant_id
        ).all()
