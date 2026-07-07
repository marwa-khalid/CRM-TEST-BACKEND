from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import List

from libdata.models.tables import HireVehicleProvided, HireDetail
from appflow.models.hire_record import HireRecordIn, HireRecordsIn, HireRecordOut


def _hvp_fields(rec: HireRecordIn) -> dict:
    return {
        "client_vehicle_category_id": rec.client_vehicle_category_id,
        "actual_vehicle_category_id": rec.actual_vehicle_category_id,
        "cross_hire": rec.cross_hire,
        "hire_vehicle_status_id": rec.hire_vehicle_status_id,
        "hire_vehicle_registration": rec.hire_vehicle_registration,
        "make": rec.make,
        "model": rec.model,
        "hire_start_date": rec.hire_start_date,
        "hire_end_date": rec.hire_end_date,
        "fuel_type": rec.fuel_type,
        "plate_transfer": rec.plate_transfer,
    }


def _det_fields(rec: HireRecordIn, hvp_id: int, claim_id: int) -> dict:
    return {
        "hire_vehicle_provided_id": hvp_id,
        "claim_id": claim_id,
        "vehicle_file_reference": rec.vehicle_file_reference,
        "abi_insurer": rec.abi_insurer,
        "abi_hire_charge_per_day": rec.abi_hire_charge_per_day,
        "abi_extra_charges_per_day": rec.abi_extra_charges_per_day,
        "admin_fee_id": rec.admin_fee_id,
        "abi_administration_fee": rec.abi_administration_fee,
        "total_abi_hire_charge": rec.total_abi_hire_charge,
        "bhr_hire_charge_per_day": rec.bhr_hire_charge_per_day,
        "bhr_extra_charges_per_day": rec.bhr_extra_charges_per_day,
        "bhr_administration_fee": rec.bhr_administration_fee,
        "cdw_charges": rec.cdw_charges,
        "collection_delivery_fee": rec.collection_delivery_fee,
        "total_bhr_charges": rec.total_bhr_charges,
        "no_of_days_hire_so_far": rec.no_of_days_hire_so_far,
        "final_total_no_of_hire_days": rec.final_total_no_of_hire_days,
    }


def _to_out(hvp: HireVehicleProvided, det) -> HireRecordOut:
    return HireRecordOut(
        id=hvp.id,
        hire_detail_id=det.id if det else None,
        client_vehicle_category_id=hvp.client_vehicle_category_id,
        actual_vehicle_category_id=hvp.actual_vehicle_category_id,
        cross_hire=hvp.cross_hire,
        hire_vehicle_status_id=hvp.hire_vehicle_status_id,
        hire_vehicle_registration=hvp.hire_vehicle_registration,
        make=hvp.make,
        model=hvp.model,
        hire_start_date=hvp.hire_start_date,
        hire_end_date=hvp.hire_end_date,
        fuel_type=hvp.fuel_type,
        plate_transfer=hvp.plate_transfer,
        vehicle_file_reference=det.vehicle_file_reference if det else None,
        abi_insurer=det.abi_insurer if det else None,
        abi_hire_charge_per_day=det.abi_hire_charge_per_day if det else None,
        abi_extra_charges_per_day=det.abi_extra_charges_per_day if det else None,
        admin_fee_id=det.admin_fee_id if det else None,
        abi_administration_fee=det.abi_administration_fee if det else None,
        total_abi_hire_charge=det.total_abi_hire_charge if det else None,
        bhr_hire_charge_per_day=det.bhr_hire_charge_per_day if det else None,
        bhr_extra_charges_per_day=det.bhr_extra_charges_per_day if det else None,
        bhr_administration_fee=det.bhr_administration_fee if det else None,
        cdw_charges=det.cdw_charges if det else None,
        collection_delivery_fee=det.collection_delivery_fee if det else None,
        total_bhr_charges=det.total_bhr_charges if det else None,
        no_of_days_hire_so_far=det.no_of_days_hire_so_far if det else None,
        final_total_no_of_hire_days=det.final_total_no_of_hire_days if det else None,
    )


class HireRecordService:

    @staticmethod
    def get_by_claim(claim_id: int, db: Session) -> List[HireRecordOut]:
        hvp_list = (
            db.query(HireVehicleProvided)
            .filter(
                HireVehicleProvided.claim_id == claim_id,
                HireVehicleProvided.is_active == True,
                HireVehicleProvided.is_deleted == False,
            )
            .order_by(HireVehicleProvided.id.asc())
            .all()
        )

        results = []
        for hvp in hvp_list:
            det = (
                db.query(HireDetail)
                .filter(HireDetail.hire_vehicle_provided_id == hvp.id)
                .first()
            )
            results.append(_to_out(hvp, det))

        return results

    @staticmethod
    def save(payload: HireRecordsIn, db: Session, current_user: int) -> List[HireRecordOut]:
        claim_id = payload.claim_id
        incoming_ids = {r.id for r in payload.records if r.id}

        # Soft-delete HVP records that are no longer in the incoming list
        existing_hvps = (
            db.query(HireVehicleProvided)
            .filter(
                HireVehicleProvided.claim_id == claim_id,
                HireVehicleProvided.is_active == True,
                HireVehicleProvided.is_deleted == False,
            )
            .all()
        )
        for hvp in existing_hvps:
            if hvp.id not in incoming_ids:
                hvp.is_active = False
                hvp.is_deleted = True
                hvp.updated_by = current_user

        hvp_det_pairs = []

        try:
            for rec in payload.records:
                if rec.id:
                    # Update existing HVP
                    hvp = db.query(HireVehicleProvided).filter(
                        HireVehicleProvided.id == rec.id
                    ).first()
                    if not hvp:
                        raise HTTPException(404, f"HireVehicleProvided id={rec.id} not found")

                    for k, v in _hvp_fields(rec).items():
                        setattr(hvp, k, v)
                    hvp.updated_by = current_user

                    # Update or create HireDetail
                    det = db.query(HireDetail).filter(
                        HireDetail.hire_vehicle_provided_id == hvp.id
                    ).first()
                    if det:
                        for k, v in _det_fields(rec, hvp.id, claim_id).items():
                            setattr(det, k, v)
                        det.updated_by = current_user
                    else:
                        det = HireDetail(**_det_fields(rec, hvp.id, claim_id))
                        det.created_by = current_user
                        det.updated_by = current_user
                        db.add(det)
                else:
                    # Create new HVP
                    hvp = HireVehicleProvided(
                        claim_id=claim_id,
                        created_by=current_user,
                        updated_by=current_user,
                        **_hvp_fields(rec),
                    )
                    db.add(hvp)
                    db.flush()  # get hvp.id before creating HireDetail

                    det = HireDetail(**_det_fields(rec, hvp.id, claim_id))
                    det.created_by = current_user
                    det.updated_by = current_user
                    db.add(det)

                hvp_det_pairs.append((hvp, det))

            db.commit()

            for hvp, det in hvp_det_pairs:
                db.refresh(hvp)
                db.refresh(det)

            return [_to_out(hvp, det) for hvp, det in hvp_det_pairs]

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(500, f"Error saving hire records: {str(e)}")
