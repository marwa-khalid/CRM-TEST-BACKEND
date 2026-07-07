from sqlalchemy.orm import Session
from libdata.models.tables import (
    HirePaymentDetails, Claim,
    HireDetail, Storage, Recovery, RouteRepair, PlatingAdditionalCharges, EngineerDetail,
)
from appflow.models.hire_payment_details import HirePaymentDetailsIn
from appflow.services.repair_total_loss_email_service import _send_email

UNDERPAYMENT_EMAIL = "ruby.uddin@nationwideassist.co.uk"


def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


class HirePaymentDetailsService:

    @staticmethod
    def get_by_claim(claim_id: int, db: Session):
        return (
            db.query(HirePaymentDetails)
            .filter(
                HirePaymentDetails.claim_id == claim_id,
                HirePaymentDetails.is_active == True,
                HirePaymentDetails.is_deleted == False,
            )
            .first()
        )

    @staticmethod
    def _get_total_incl_vat(claim_id: int, db: Session) -> float:
        hire = (
            db.query(HireDetail)
            .filter(HireDetail.claim_id == claim_id, HireDetail.is_deleted == False)
            .first()
        )
        hire_days = _f(hire.final_total_no_of_hire_days or hire.no_of_days_hire_so_far if hire else None)
        hire_rate = _f(hire.abi_hire_charge_per_day if hire else None)
        admin_fee = _f(hire.abi_administration_fee if hire else None)
        cdw = _f(hire.cdw_charges if hire else None)
        cd_fee = _f(hire.collection_delivery_fee if hire else None)

        storages = (
            db.query(Storage)
            .filter(Storage.claim_id == claim_id, Storage.is_deleted == False)
            .all()
        )
        total_storage = sum(_f(s.total_storage_charges) for s in storages)

        repair = (
            db.query(RouteRepair)
            .filter(RouteRepair.claim_id == claim_id, RouteRepair.is_deleted == False)
            .first()
        )
        repair_cost = _f(repair.total_inc_vat if repair else None)

        recoveries = (
            db.query(Recovery)
            .filter(Recovery.claim_id == claim_id, Recovery.is_deleted == False)
            .all()
        )
        total_recovery = sum(_f(r.recovery_charges) for r in recoveries)

        plating = (
            db.query(PlatingAdditionalCharges)
            .filter(PlatingAdditionalCharges.claim_id == claim_id, PlatingAdditionalCharges.is_deleted == False)
            .first()
        )
        plating_cost = _f(plating.total_plating_cost if plating else None)

        engineer = (
            db.query(EngineerDetail)
            .filter(EngineerDetail.claim_id == claim_id, EngineerDetail.is_deleted == False)
            .first()
        )
        engineer_fee = _f(engineer.engineer_fee if engineer else None)

        excl_vat = (
            hire_days * hire_rate + admin_fee + total_storage + repair_cost +
            total_recovery + plating_cost + engineer_fee + cdw + cd_fee
        )
        return excl_vat * 1.2

    @staticmethod
    def save(payload: HirePaymentDetailsIn, db: Session, current_user: int):
        existing = HirePaymentDetailsService.get_by_claim(payload.claim_id, db)
        if existing:
            for k, v in payload.model_dump(exclude={"claim_id"}).items():
                setattr(existing, k, v)
            existing.updated_by = current_user
            db.commit()
            db.refresh(existing)
            record = existing
        else:
            record = HirePaymentDetails(
                **payload.model_dump(),
                created_by=current_user,
                updated_by=current_user,
            )
            db.add(record)
            db.commit()
            db.refresh(record)

        # Send underpayment alert if payment_amount < total actual incl. VAT
        if payload.payment_amount is not None:
            total_incl_vat = HirePaymentDetailsService._get_total_incl_vat(payload.claim_id, db)
            if _f(payload.payment_amount) < total_incl_vat:
                claim = db.query(Claim).filter(Claim.id == payload.claim_id).first()
                case_ref = getattr(claim, "our_reference", "") or str(payload.claim_id)
                outstanding = total_incl_vat - _f(payload.payment_amount)
                html = (
                    f"<p>Case Reference: <strong>{case_ref}</strong></p>"
                    f"<p>Total Actual Amount (Incl. VAT): <strong>£{total_incl_vat:.2f}</strong></p>"
                    f"<p>Amount Received: <strong>£{_f(payload.payment_amount):.2f}</strong></p>"
                    f"<p>Outstanding Difference: <strong>£{outstanding:.2f}</strong></p>"
                )
                try:
                    _send_email(
                        to_email=UNDERPAYMENT_EMAIL,
                        subject=f"Underpayment Alert – {case_ref}",
                        html_content=html,
                    )
                except Exception:
                    pass

        return record
