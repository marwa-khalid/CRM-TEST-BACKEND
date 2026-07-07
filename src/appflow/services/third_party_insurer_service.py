from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from appflow.models.third_party_insurer import ThirdPartyInsurerIn
from libdata.models.tables import ThirdPartyInsurer, ClientDetail, Address, LiabilityStance
from libdata.enums import PersonRoleEnum,HistoryLogType
from appflow.utils import get_tenant_id,actor_id,build_case_reference
from appflow.services.history_activity_service import HistoryActivityService
from datetime import datetime, date


class ThirdPartyInsurerService:

    @staticmethod
    def create_client_detail(client_data, claim_id, tenant_id, role, db: Session):
        """Helper to create ClientDetail with  address"""
        if not client_data:
            return None

        address_id = None
        if client_data.address:
            db_address = Address(**client_data.address.dict())
            db.add(db_address)
            db.flush()
            db.refresh(db_address)
            address_id = db_address.id

        db_client = ClientDetail(
            gender=client_data.gender,
            first_name=client_data.first_name,
            surname=client_data.surname,
            tenant_id=tenant_id,
            claim_id=claim_id,
            address_id=address_id,
            role=role.value,
        )
        db.add(db_client)
        db.flush()
        db.refresh(db_client)
        return db_client

    @staticmethod
    def update_client_detail(client_id, client_data, db: Session):
        """Helper to update ClientDetail and its address"""
        updated_fields = []
        if not client_data:
            return updated_fields

        db_client = db.query(ClientDetail).filter(ClientDetail.id == client_id).first()
        if not db_client:
            return updated_fields

        # Compare and update main client fields
        for field in ["gender", "first_name", "surname"]:
            new_value = getattr(client_data, field, None)
            old_value = getattr(db_client, field)
            if new_value == "":
                new_value = None
            if new_value is not None and new_value != old_value:
                setattr(db_client, field, new_value)
                updated_fields.append(field)

        # Compare and update address
        if client_data.address:
            if db_client.address_id:
                db_address = db.query(Address).filter(Address.id == db_client.address_id).first()
                if db_address:
                    for key, value in client_data.address.dict(exclude_unset=True).items():
                        if value == "":
                            value = None
                        old_value = getattr(db_address, key, None)
                        if value != old_value:
                            setattr(db_address, key, value)
                            updated_fields.append(f"{key}")

            # Compare and update address
            if client_data.address:
                if db_client.address_id:
                    db_address = db.query(Address).filter(Address.id == db_client.address_id).first()
                    if db_address:
                        for key, value in client_data.address.dict(exclude_unset=True).items():
                            old_value = getattr(db_address, key, None)
                            if value != old_value:
                                setattr(db_address, key, value)
                                updated_fields.append(f"{key}")
                    else:
                        db_address = Address(**client_data.address.dict())
                        db.add(db_address)
                        db.flush()
                        db_client.address_id = db_address.id
                        updated_fields.extend([f"{k}" for k in client_data.address.dict().keys()])
                else:
                    db_address = Address(**client_data.address.dict())
                    db.add(db_address)
                    db.flush()
                    db_client.address_id = db_address.id
                    updated_fields.extend([f"{k}" for k in client_data.address.dict().keys()])

        db.flush()
        db.refresh(db_client)
        return updated_fields

    @staticmethod
    def _validate_liability(payload: ThirdPartyInsurerIn, db: Session):
        """Ensure liability_accepted_on is required if stance=Accepted or Fault"""
        if payload.liability_stance_id:
            stance = db.query(LiabilityStance).filter(LiabilityStance.id == payload.liability_stance_id).first()
            if stance and stance.label.upper() in ["ACCEPTED", "FAULT"]:
                if not payload.liability_accepted_on:
                    raise HTTPException(
                        status_code=400,
                        detail="liability_accepted_on is required when stance is Accepted or Fault"
                    )

    @staticmethod
    def create_third_party_insurer(request: Request, payload: ThirdPartyInsurerIn, db: Session):
        tenant_id = get_tenant_id(request)
        current_user_id = actor_id(request)

        ThirdPartyInsurerService._validate_liability(payload, db)

        # Create related ClientDetails
        third_party = ThirdPartyInsurerService.create_client_detail(
            payload.third_party, payload.claim_id, tenant_id, PersonRoleEnum.THIRD_PARTY, db
        )
        third_party_insurer = ThirdPartyInsurerService.create_client_detail(
            payload.third_party_insurer, payload.claim_id, tenant_id, PersonRoleEnum.THIRD_PARTY_INSURER, db
        )
        third_party_handling = ThirdPartyInsurerService.create_client_detail(
            payload.third_party_handling, payload.claim_id, tenant_id, PersonRoleEnum.THIRD_PARTY_HANDLING, db
        )

        db_obj = ThirdPartyInsurer(
            **payload.dict(exclude={"third_party", "third_party_insurer", "third_party_handling"}),
            third_party_id=third_party.id if third_party else None,
            third_party_insurer_id=third_party_insurer.id if third_party_insurer else None,
            third_party_handling_id=third_party_handling.id if third_party_handling else None,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        reference = build_case_reference(payload.claim_id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=payload.claim_id,
            file_name=f"The third party insurer detail has been created for claim {reference}",
            file_path="",
            file_type=HistoryLogType.CREATED_THIRD_INSURER,
            user_id=current_user_id,
            tenant_id=tenant_id
        )
        return db_obj

    @staticmethod
    def update_third_party_insurer(claim_id: int, payload: ThirdPartyInsurerIn, db: Session,request):
        current_user_id = actor_id(request)
        tenant_id = get_tenant_id(request)
        db_obj = db.query(ThirdPartyInsurer).filter(
            ThirdPartyInsurer.claim_id == claim_id,
            ThirdPartyInsurer.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Third Party Insurer not found")

        ThirdPartyInsurerService._validate_liability(payload, db)

        updated_fields = []
        FIELD_READABLE_MAP = {
            "abi_insured": "ABI Insured",
            "claim_validation": "Client's Claim in Validation?",
            "direct_email": "Direct Email",
            "handler_id": "Conducting the new MID",
            "handling_reference": "Third Party Handling Reference",
            "incorrect_acc": "Incorrect ACC",
            "incorrect_mid_reference": "Incorrect MID Reference",
            "incorrect_reg": "Incorrect Reg",
            "initial_eng_made": "Initial Eng Made",
            "insurer_reference": "Third Party Insurer Reference",
            "liability_accepted_on": "Liability Accepted On",
            "liability_stance_id": "Liability Stance",
            "new_mid": "New MID Conduct",
            "new_mid_search_processed": "New MID Search Processed?",
            "new_mid_search_ref": "New MID Search Ref",
            "policy_number": "Policy Number",
            "reason_new_mid_id": "Reason for New MID?",
            "settlement_status_id": "Settlement Status",
            "third_party.address": "Third Party Address",
            "third_party.postcode":"Third Party Postcode",
            "third_party.email":"Third Party Email",
            "third_party.mobile_tel":"Third Party Telephone Main",
            "third_party.first_name": "Third Party First Name",
            "third_party.gender": "Third Party Gender",
            "third_party.surname": "Third Party Surname",
            "third_party_handling.address": "Third Party Handling Address",
            "third_party_insurer.mobile_tel": "Third Party Insurer Telephone Main",
            "third_party_handling.postcode": "Third Party Handling Postcode",
            "third_party_handling.email":"Third Party Handling Email",
            "third_party_handling.first_name": "Third Party Handling First Name",
            "third_party_handling.gender": "Third Party Handling Gender",
            "third_party_handling.surname": "Third Party Handling Surname",
            "third_party_insurer.address": "Third Party Insurer Address",
            "third_party_handling.mobile_tel": "Third Party Handling Telephone Main",
            "third_party_insurer.email":"Third Party Insurer General Email",
            " third_party_insurer.postcode": "Third Party Insurer Postcode",
            "third_party_insurer.first_name": "Third Party Insurer First Name",
            "third_party_insurer.gender": "Third Party Insurer Gender",
            "third_party_insurer.surname": "Third Party Insurer Surname",
        }

        # Update related clients
        if payload.third_party:
            changed = ThirdPartyInsurerService.update_client_detail(db_obj.third_party_id, payload.third_party, db)
            updated_fields.extend([f"third_party.{f}" for f in changed])

        if payload.third_party_insurer:
            changed = ThirdPartyInsurerService.update_client_detail(db_obj.third_party_insurer_id,payload.third_party_insurer, db)
            updated_fields.extend([f"third_party_insurer.{f}" for f in changed])

        if payload.third_party_handling:
            changed = ThirdPartyInsurerService.update_client_detail(db_obj.third_party_handling_id,payload.third_party_handling, db)
            updated_fields.extend([f"third_party_handling.{f}" for f in changed])

        # Update main ThirdPartyInsurer fields
        update_data = payload.dict(exclude_unset=True,
                                   exclude={"third_party", "third_party_insurer", "third_party_handling"})
        for key, value in update_data.items():
            old_value = getattr(db_obj, key)

            # Convert empty string to None to match current db representation
            if value == "":
                value = None

            if value != old_value:
                setattr(db_obj, key, value)
                updated_fields.append(key)

        db.commit()
        db.refresh(db_obj)
        reference = build_case_reference(claim_id,db)
        if updated_fields:
            readable_fields = [FIELD_READABLE_MAP.get(f, f) for f in sorted(set(updated_fields))]
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim_id,
                file_name=f"The third party insurer detail has been updated for claim {reference}",
                file_path=f"{', '.join(readable_fields)}",
                file_type=HistoryLogType.UPDATED_THIRD_INSURER,
                user_id=current_user_id,
                tenant_id=tenant_id
            )
        return db_obj

    @staticmethod
    def get_third_party_insurer(claim_id: int, db: Session):
        db_obj = db.query(ThirdPartyInsurer).filter(
            ThirdPartyInsurer.claim_id == claim_id,
            ThirdPartyInsurer.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Third Party Insurer not found or inactive")

        return db_obj

    @staticmethod
    def deactivate_third_party_insurer(claim_id: int, db: Session):
        db_obj = db.query(ThirdPartyInsurer).filter(
            ThirdPartyInsurer.claim_id == claim_id,
            ThirdPartyInsurer.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Third Party Insurer not found or already inactive")

        db_obj.is_active = False
        db.commit()
        return {"message": "Third Party Insurer deactivated successfully"}
