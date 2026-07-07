from sqlalchemy.orm import Session
from libdata.models.tables import ABIBHRCharges
from appflow.models.abi_bhr_charges import ABIBHRChargesIn
from appflow.utils import build_invoice_reference


class ABIBHRChargesService:

    @staticmethod
    def get_by_claim(claim_id: int, db: Session):
        record = (
            db.query(ABIBHRCharges)
            .filter(
                ABIBHRCharges.claim_id == claim_id,
                ABIBHRCharges.is_active == True,
                ABIBHRCharges.is_deleted == False,
            )
            .first()
        )
        # Reserve + persist the invoice reference so the payment screen always
        # shows a stored value (never editable). Created on first view if needed.
        if record is None:
            record = ABIBHRCharges(
                claim_id=claim_id,
                invoice_number=build_invoice_reference(claim_id),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
        elif not record.invoice_number:
            record.invoice_number = build_invoice_reference(claim_id)
            db.commit()
            db.refresh(record)
        return record

    @staticmethod
    def save(payload: ABIBHRChargesIn, db: Session, current_user: int):
        existing = ABIBHRChargesService.get_by_claim(payload.claim_id, db)
        if existing:
            existing.payment_pack_raised_date = payload.payment_pack_raised_date
            existing.payment_pack_sent_date = payload.payment_pack_sent_date
            # invoice_number is auto-generated/stored — keep it stable, never
            # overwrite it from the client payload.
            if not existing.invoice_number:
                existing.invoice_number = build_invoice_reference(payload.claim_id)
            existing.date_hire_paid = payload.date_hire_paid
            existing.updated_by = current_user
            db.commit()
            db.refresh(existing)
            return existing
        record = ABIBHRCharges(
            claim_id=payload.claim_id,
            payment_pack_raised_date=payload.payment_pack_raised_date,
            payment_pack_sent_date=payload.payment_pack_sent_date,
            invoice_number=build_invoice_reference(payload.claim_id),
            date_hire_paid=payload.date_hire_paid,
            created_by=current_user,
            updated_by=current_user,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
