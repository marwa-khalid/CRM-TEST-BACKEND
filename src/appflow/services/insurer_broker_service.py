from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from libdata.models.tables import InsurerBroker, Claim, Address, ClientDetail
from libdata.enums import PersonRoleEnum
from appflow.models.insurer_broker import InsurerBrokerIn
from appflow.utils import build_case_reference
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType

class InsurerBrokerService:

    @staticmethod
    def get_insurer_by_claim_id(claim_id: int, db: Session):
        insurers = db.query(InsurerBroker).options(
            joinedload(InsurerBroker.policy_type),
            joinedload(InsurerBroker.policy_cover),
            joinedload(InsurerBroker.claim),
            joinedload(InsurerBroker.claim),
        ).filter(InsurerBroker.claim_id == claim_id).all()

        if not insurers:
            raise HTTPException(status_code=404, detail="No insurer brokers found for this claim")
        return insurers

    @staticmethod
    def get_insurer_by_company_name(company_name: str, db: Session):
        insurers = db.query(InsurerBroker).options(
            joinedload(InsurerBroker.policy_type),
            joinedload(InsurerBroker.policy_cover)
        ).filter(InsurerBroker.company_name.ilike(f"%{company_name}%")).all()

        if not insurers:
            raise HTTPException(status_code=404, detail="No insurer brokers found for this company")
        return insurers

    @staticmethod
    def create_insurer(insurer: InsurerBrokerIn, db: Session, tenant_id: int, current_user_id: int):
        claim = db.query(Claim).filter(
            Claim.id == insurer.claim_id
        ).first()
        print(tenant_id)
        print(claim)
        print(insurer.claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        try:
            insurer_data = insurer.dict()

            # Handle nested address
            address_data = insurer_data.pop("address", None)
            if address_data:
                address = Address(**address_data,created_by=current_user_id,updated_by=current_user_id)
                db.add(address)
                db.flush()
                insurer_data["address_id"] = address.id

            # --- Ensure policy_holder matches ClientDetail (Vehicle Owner) ---
            vehicle_owner = (
                db.query(ClientDetail)
                .filter(
                    ClientDetail.claim_id == insurer.claim_id,
                    ClientDetail.role == PersonRoleEnum.VEHICLE_OWNER
                )
                .first()
            )

            # if vehicle_owner:
            #     expected_holder = f"{vehicle_owner.first_name} {vehicle_owner.surname}".strip()
            #     provided_holder = insurer.policy_holder.strip()
            #
            #     if expected_holder.lower() != provided_holder.lower():
            #         # Update clientdetail to match policy_holder
            #         parts = provided_holder.split(" ", 1)
            #         vehicle_owner.first_name = parts[0]
            #         vehicle_owner.surname = parts[1] if len(parts) > 1 else ""
            #         db.add(vehicle_owner)
            if vehicle_owner:
                # safe expected holder (guard against None first_name/surname)
                expected_first = (vehicle_owner.first_name or "").strip()
                expected_last = (vehicle_owner.surname or "").strip()
                expected_holder = f"{expected_first} {expected_last}".strip()

                # SAFE: use raw insurer_data value (may be None), convert to empty string if falsy, then strip
                provided_holder = (insurer_data.get("policy_holder") or "").strip()

                # Only attempt comparison/update if provided_holder contains something meaningful
                if provided_holder:
                    if expected_holder.lower() != provided_holder.lower():
                        parts = provided_holder.split(" ", 1)
                        vehicle_owner.first_name = parts[0] if parts[0] is not None else ""
                        vehicle_owner.surname = parts[1] if len(parts) > 1 else ""
                        db.add(vehicle_owner)

            new_insurer = InsurerBroker(
                **insurer_data,
                tenant_id=tenant_id,
                created_by=current_user_id,
                updated_by=current_user_id
            )
            db.add(new_insurer)
            db.commit()
            db.refresh(new_insurer)
            reference = build_case_reference(claim.id,db)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim.id,
                file_name=f"The insurer broker detail has been created for claim {reference}",
                file_path="",
                file_type=HistoryLogType.CREATED_INSURER_BROKER,
                user_id=current_user_id,
                tenant_id=tenant_id
            )
            return new_insurer

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creating insurer broker: {str(e)}")

    @staticmethod
    def update_insurer(claim_id: int, insurer: InsurerBrokerIn, db: Session, tenant_id: int, current_user_id: int):
        existing = db.query(InsurerBroker).filter(
            InsurerBroker.claim_id == claim_id,
            # InsurerBroker.claim.has(tenant_id=tenant_id)
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Insurer broker not found")

        changed_fields = []
        field_label_map = {
            "policy_holder": "Policy Holder",
            "address.address": "Address",
            "address.postcode": "Postcode",
            "address.mobile_tel": "Telephone",
            "address.email": "Email",
            "company_name": "Company Name",
            "reference": "Reference",
            "policy_number": "Policy Number",
            "number_of_additional_driver": "Number of Additional Drivers",
            "number_vehicle_on_policy": "Number of Vehicles on Policy",
            "number_vehicle_in_use": "Number of Vehicles in Use",
            "policy_cover_excess": "Policy Cover Excess",
            "sdp":"SDP",
            "private_hire":"Private Hire/Hackney",
            "policy_type_id": "Type of Policy",
            "policy_cover_id":"Policy Cover Level"
        }

        try:
            insurer_data = insurer.dict(exclude_unset=True)

            # --- Ensure policy_holder matches ClientDetail (Vehicle Owner) ---
            vehicle_owner = (
                db.query(ClientDetail)
                .filter(
                    ClientDetail.claim_id == claim_id,
                    ClientDetail.role == PersonRoleEnum.VEHICLE_OWNER
                )
                .first()
            )

            # if vehicle_owner and "policy_holder" in insurer_data:
            #     expected_holder = f"{vehicle_owner.first_name} {vehicle_owner.surname}".strip()
            #     provided_holder = insurer_data["policy_holder"].strip()
            #     if expected_holder.lower() != provided_holder.lower():
            #         parts = provided_holder.split(" ", 1)
            #         vehicle_owner.first_name = parts[0]
            #         vehicle_owner.surname = parts[1] if len(parts) > 1 else ""
            #         db.add(vehicle_owner)
            #         changed_fields.append("policy_holder")
            if vehicle_owner and "policy_holder" in insurer_data:
                # SAFELY normalize incoming policy holder
                provided_holder = (insurer_data.get("policy_holder") or "").strip()

                # If empty → skip matching entirely
                if provided_holder:
                    expected_first = (vehicle_owner.first_name or "").strip()
                    expected_last = (vehicle_owner.surname or "").strip()
                    expected_holder = f"{expected_first} {expected_last}".strip()

                    if expected_holder.lower() != provided_holder.lower():
                        parts = provided_holder.split(" ", 1)
                        vehicle_owner.first_name = parts[0]
                        vehicle_owner.surname = parts[1] if len(parts) > 1 else ""
                        db.add(vehicle_owner)
                        # changed_fields.append("policy_holder")

            # --- Update nested address if provided ---
            address_data = insurer_data.pop("address", None)
            if address_data:
                if existing.address_id:
                    address = db.query(Address).filter(Address.id == existing.address_id).first()
                    if address:
                        for key, value in address_data.items():
                            old_value = getattr(address, key)
                            if old_value != value:
                                setattr(address, key, value)
                                address.updated_by = current_user_id
                                changed_fields.append(f"address.{key}")
                else:
                    new_address = Address(**address_data)
                    db.add(new_address)
                    db.flush()
                    existing.address_id = new_address.id
                    changed_fields.append("address")

            # --- Update other fields ---
            for key, value in insurer_data.items():
                old_value = getattr(existing, key)
                if old_value != value:
                    setattr(existing, key, value)
                    changed_fields.append(key)
            existing.updated_by=current_user_id
            db.commit()
            db.refresh(existing)
            if changed_fields:
                readable_changes = [field_label_map.get(f, f) for f in changed_fields]
                file_path = ", ".join(readable_changes)
                reference = build_case_reference(claim_id,db)
                HistoryActivityService.create_activity(
                    db=db,
                    claim_id=claim_id,
                    file_name=f"The insurer broker detail has been updated for claim {reference}",
                    file_path=file_path,
                    file_type=HistoryLogType.UPDATED_INSURER_BROKER,
                    user_id=current_user_id,
                    tenant_id=tenant_id
                )
            return existing

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error updating insurer broker: {str(e)}")

    @staticmethod
    def deactivate_insurer(insurer_id: int, db: Session, tenant_id: int):
        insurer = db.query(InsurerBroker).filter(
            InsurerBroker.id == insurer_id,
            InsurerBroker.claim.has(tenant_id=tenant_id)
        ).first()

        if not insurer:
            raise HTTPException(status_code=404, detail="Insurer broker not found")

        try:
            insurer.is_active = False
            db.commit()
            db.refresh(insurer)
            return {"detail": "Insurer broker deactivated successfully"}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error deactivating insurer broker: {str(e)}")

    @staticmethod
    def search_insurers(query: str, db: Session, tenant_id: int):
        return db.query(InsurerBroker).filter(
            InsurerBroker.company_name.ilike(f"%{query}%"),
            InsurerBroker.claim.has(tenant_id=tenant_id)
        ).all()

    @staticmethod
    def get_policy_holder_by_claim(db: Session, claim_id: int):
        client = (
            db.query(ClientDetail)
            .filter(
                ClientDetail.claim_id == claim_id,
                ClientDetail.role == PersonRoleEnum.VEHICLE_OWNER
            )
            .first()
        )
        if client:
            return f"{client.first_name} {client.surname}".strip()
        return None

