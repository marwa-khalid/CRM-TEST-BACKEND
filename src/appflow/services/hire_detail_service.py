from appflow.models.hire_detail import HireDetailOut
from fastapi import HTTPException
from libdata.models.tables import HireDetail, ActualVehicleCategory,HireVehicleProvided
from sqlalchemy.orm import Session
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType
from appflow.models.hire_detail import HireDetailDisplayLabels
from appflow.utils import build_case_reference

class HireDetailService:

    @staticmethod
    def create_hire_details(data, db: Session,current_user,tenant_id):
        """
        Create hire details.
        - If only one record: validate ABI insurer rules.
        - If multiple: ensure previous record has hire_back before next.
        - Auto-fill ABI/BHR rates from ActualVehicleCategory.
        """
        created_items = []

        for index, item in enumerate(data.hire_details):
            # --- ABI insurer validation ---
            if item.abi_insurer:
                missing_fields = [
                    f for f in ["abi_extra_charges_per_day","admin_fee_id", "abi_administration_fee", "total_abi_hire_charge"]
                    if getattr(item, f, None) is None
                ]
                if missing_fields:
                    raise HTTPException(
                        status_code=400,
                        detail=f"When 'abi_insurer' is True, these fields are required: {', '.join(missing_fields)}"
                    )

            # --- Multi-record validation ---
            if index > 0:
                prev_item = data.hire_details[index - 1]
                if prev_item.hire_back is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot create record {index + 1}: previous record has no 'hire_back'."
                    )

            hire_detail = HireDetail(
                hire_vehicle_provided_id=item.hire_vehicle_provided_id,
                hire_out=item.hire_out,
                hire_back=item.hire_back,
                no_of_days_hire_so_far=item.no_of_days_hire_so_far,
                final_total_no_of_hire_days=item.final_total_no_of_hire_days,
                vehicle_file_reference=item.vehicle_file_reference,
                # registration_number=item.registration_number,
                # make=item.make,
                # model=item.model,
                abi_insurer=item.abi_insurer,
                abi_hire_charge_per_day=item.abi_hire_charge_per_day,  # FROM PAYLOAD
                abi_extra_charges_per_day=item.abi_extra_charges_per_day,
                admin_fee_id=item.admin_fee_id,
                abi_administration_fee=item.abi_administration_fee,
                total_abi_hire_charge=item.total_abi_hire_charge,
                bhr_hire_charge_per_day=item.bhr_hire_charge_per_day,  # FROM PAYLOAD
                bhr_extra_charges_per_day=item.bhr_extra_charges_per_day,
                bhr_administration_fee=item.bhr_administration_fee,
                cdw_charges=item.cdw_charges,
                collection_delivery_fee=item.collection_delivery_fee,
                total_bhr_charges=item.total_bhr_charges,
                claim_id=item.claim_id,
                is_active=True,
                created_by=current_user,
                updated_by=current_user
            )
            db.add(hire_detail)
            created_items.append(hire_detail)

        db.commit()
        for item in created_items:
            db.refresh(item)
            reference = build_case_reference(item.claim_id,db)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=item.claim_id,
                file_name=f"The hire detail has been created for claim {reference}",
                file_path="",
                file_type=HistoryLogType.CREATED_HIRE_DETAIL,
                user_id=current_user,
                tenant_id=tenant_id
            )
        return created_items

    # ----------------------------------------------------------------------

    @staticmethod
    def get_hire_details_by_claim_id(claim_id: int, db: Session):
        hire_details = (
            db.query(HireDetail)
            .filter(HireDetail.claim_id == claim_id, HireDetail.is_active.is_(True))
            .order_by(HireDetail.id.asc())
            .all()
        )
        if not hire_details:
            raise HTTPException(status_code=404, detail="No active hire details found for this claim.")
        return hire_details

    # ----------------------------------------------------------------------

    @staticmethod
    def update_hire_details_by_claim_id(
            claim_id: int,
            hire_details_data,
            db: Session,
            current_user,
            tenant_id
    ):
        existing_records = (
            db.query(HireDetail)
            .filter(
                HireDetail.claim_id == claim_id,
                HireDetail.is_active == True,
                HireDetail.is_deleted == False
            )
            .order_by(HireDetail.id.asc())
            .all()
        )

        incoming_records = hire_details_data.hire_details

        updated_rows = []
        updated_fields = []

        max_len = max(len(existing_records), len(incoming_records))

        for i in range(max_len):

            # ---------------- UPDATE EXISTING ----------------
            if i < len(existing_records) and i < len(incoming_records):
                db_obj = existing_records[i]
                payload = incoming_records[i].dict(exclude_unset=True)

                changed_fields = []

                for key, value in payload.items():
                    if hasattr(db_obj, key):
                        old_value = getattr(db_obj, key)
                        if old_value != value:
                            setattr(db_obj, key, value)
                            changed_fields.append(
                                HireDetailDisplayLabels.format(key)
                            )

                if changed_fields:
                    updated_fields.extend(changed_fields)
                    db_obj.updated_by = current_user

                updated_rows.append(db_obj)

            # ---------------- SOFT DELETE ----------------
            elif i < len(existing_records) and i >= len(incoming_records):
                db_obj = existing_records[i]
                db_obj.is_active = False
                db_obj.is_deleted = True
                db_obj.updated_by = current_user

                updated_fields.append("Hire Detail Deleted")
                updated_rows.append(db_obj)

            # ---------------- CREATE NEW ----------------
            elif i >= len(existing_records) and i < len(incoming_records):
                payload = incoming_records[i].dict(exclude_unset=True)

                new_obj = HireDetail(
                    **payload,
                    # claim_id=claim_id,
                    is_active=True,
                    is_deleted=False,
                    created_by=current_user,
                    updated_by=current_user
                )
                db.add(new_obj)
                db.flush()

                updated_fields.append("New Hire Detail Created")
                updated_rows.append(new_obj)

        db.commit()

        for r in updated_rows:
            db.refresh(r)

        # ---------------- HISTORY ACTIVITY ----------------
        if updated_fields:
            reference = build_case_reference(claim_id, db)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim_id,
                file_name=f"The hire detail has been updated for claim {reference}",
                file_path=", ".join(sorted(set(updated_fields))),
                file_type=HistoryLogType.UPDATED_HIRE_DETAIL,
                user_id=current_user,
                tenant_id=tenant_id
            )

        return [HireDetailOut.from_orm(r) for r in updated_rows]

    # @staticmethod
    # def update_hire_details_by_claim_id(claim_id: int, hire_details_data, db: Session, current_user, tenant_id):
    #
    #     existing_records = (
    #         db.query(HireDetail)
    #         .filter(HireDetail.claim_id == claim_id, HireDetail.is_active == True)
    #         .order_by(HireDetail.id.asc())
    #         .all()
    #     )
    #
    #     incoming_records = hire_details_data.hire_details
    #
    #     updated_rows = []
    #     changed_fields = []
    #
    #     max_len = max(len(existing_records), len(incoming_records))
    #
    #     for i in range(max_len):
    #
    #
    #         if i < len(existing_records) and i < len(incoming_records):
    #             db_obj = existing_records[i]
    #             payload = incoming_records[i].dict()
    #
    #             for key, value in payload.items():
    #                 if hasattr(db_obj, key):
    #                     old = getattr(db_obj, key)
    #                     if old != value:
    #                         setattr(db_obj, key, value)
    #                         changed_fields.append(HireDetailDisplayLabels.format(key))
    #
    #             db_obj.updated_by = current_user
    #             updated_rows.append(db_obj)
    #
    #
    #         elif i < len(existing_records) and i >= len(incoming_records):
    #             db_obj = existing_records[i]
    #             db_obj.is_active = False
    #             db_obj.is_deleted = True
    #             db_obj.updated_by = current_user
    #             updated_rows.append(db_obj)
    #
    #
    #         elif i >= len(existing_records) and i < len(incoming_records):
    #             payload = incoming_records[i].dict()
    #             new_obj = HireDetail(
    #                 **payload,
    #                 is_active=True,
    #                 is_deleted=False,
    #                 created_by=current_user,
    #                 updated_by=current_user
    #             )
    #             db.add(new_obj)
    #             updated_rows.append(new_obj)
    #
    #             reference = build_case_reference(claim_id, db)
    #
    #             HistoryActivityService.create_activity(
    #                 db=db,
    #                 claim_id=claim_id,
    #                 file_name=f"The hire detail has been updated for claim {reference}",
    #                 file_path=", ".join(HireDetailDisplayLabels.format(k) for k in payload.keys()),
    #                 file_type=HistoryLogType.UPDATED_HIRE_DETAIL,
    #                 user_id=current_user,
    #                 tenant_id=tenant_id
    #             )
    #
    #     db.commit()
    #
    #     for r in updated_rows:
    #         db.refresh(r)
    #
    #     if changed_fields:
    #         reference = build_case_reference(claim_id, db)
    #         HistoryActivityService.create_activity(
    #             db=db,
    #             claim_id=claim_id,
    #             file_name=f"The hire detail has been updated for claim {reference}",
    #             file_path=", ".join(changed_fields),
    #             file_type=HistoryLogType.UPDATED_HIRE_DETAIL,
    #             user_id=current_user,
    #             tenant_id=tenant_id
    #         )
    #
    #     return [HireDetailOut.from_orm(r) for r in updated_rows]

    # ----------------------------------------------------------------------

    @staticmethod
    def deactivate_hire_details_by_claim_id(claim_id: int, db: Session):
        """Deactivate all hire details for a claim."""
        records = db.query(HireDetail).filter(HireDetail.claim_id == claim_id).all()
        if not records:
            raise HTTPException(status_code=404, detail="No hire details found for this claim.")

        for record in records:
            record.is_active = False
        db.commit()
        return {"message": f"All hire details for claim_id {claim_id} have been deactivated."}

    @staticmethod
    def get_rates_from_hvp(hvp_id: int, db: Session):
        hvp = db.query(HireVehicleProvided).filter(
            HireVehicleProvided.id == hvp_id
        ).first()

        if not hvp:
            raise HTTPException(status_code=404, detail="Hire Vehicle Provided record not found.")

        category = db.query(ActualVehicleCategory).filter(
            ActualVehicleCategory.id == hvp.actual_vehicle_category_id
        ).first()

        if not category:
            raise HTTPException(status_code=404, detail="No Actual Vehicle Category linked to this HVP.")

        return {
            "hire_vehicle_provided_id": hvp_id,
            "actual_vehicle_category_id": category.id,
            "abi_hire_charge_per_day": category.abi_rate,
            "bhr_hire_per_day": category.bhr_rate
        }