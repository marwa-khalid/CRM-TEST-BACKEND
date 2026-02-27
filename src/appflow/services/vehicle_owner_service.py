# from fastapi import Request, HTTPException
# from sqlalchemy.orm import Session
# from libdata.enums import PersonRoleEnum,HistoryLogType
# from libdata.models.tables import ClientDetail, Address,InsurerBroker
# from appflow.models.vehicle_owner import VehicleOwnerIn
# from appflow.utils import get_tenant_id,build_case_reference,actor_id
# from appflow.services.history_activity_service import HistoryActivityService

# def create_vehicle_owner_service(request: Request, owner: VehicleOwnerIn, db: Session, role: PersonRoleEnum):
#     tenant_id = get_tenant_id(request)
#     current_user = actor_id(request)

#     # # ✅ Validation rules for VEHICLE_OWNER
#     # required_fields = {
#     #     "first_name": owner.first_name,
#     #     "surname": owner.surname,
#     # }
#     # missing = [f for f, v in required_fields.items() if not v]
#     # if missing:
#     #     raise HTTPException(status_code=422, detail=f"Missing required fields for VEHICLE_OWNER: {', '.join(missing)}")

#     # Check if insurer exists for the same claim
#     insurer = db.query(InsurerBroker).filter(
#         InsurerBroker.claim_id == owner.claim_id,
#         InsurerBroker.tenant_id == tenant_id
#     ).first()

#     full_name = f"{owner.first_name} {owner.surname}".strip()

#     if insurer:
#         existing_name = insurer.policy_holder.strip().lower() if insurer.policy_holder else ""
#         new_name = full_name.lower()

#         if existing_name != new_name:
#             insurer.policy_holder = full_name
#             db.add(insurer)

#     # Save address if provided
#     address_id = None
#     if owner.address:
#         db_address = Address(**owner.address.dict())
#         db.add(db_address)
#         db.flush()
#         db.refresh(db_address)
#         address_id = db_address.id

#     # Save Vehicle Owner in ClientDetail table
#     db_owner = ClientDetail(
#         **owner.dict(exclude={"address", "tenant_id"}),
#         tenant_id=tenant_id,
#         address_id=address_id,
#         role=role.value,
#         created_by=current_user,
#         updated_by=current_user
#     )
#     db.add(db_owner)
#     db.commit()
#     db.refresh(db_owner)
#     reference = build_case_reference(owner.claim_id,db)
#     HistoryActivityService.create_activity(
#         db=db,
#         claim_id=owner.claim_id,
#         file_name=f"The vehicle owner detail has been created for claim {reference}",
#         file_path="",
#         file_type=HistoryLogType.CREATED_VEHICLE_OWNER,
#         user_id=current_user,
#         tenant_id=tenant_id
#     )

#     return db_owner


# def list_vehicle_owner_service(request: Request, db: Session, role: PersonRoleEnum):
#     tenant_id = get_tenant_id(request)
#     return db.query(ClientDetail).filter(ClientDetail.tenant_id == tenant_id, ClientDetail.role == role).all()


# def get_vehicle_owner_service(claim_id: int, request: Request, db: Session, role: PersonRoleEnum):
#     tenant_id = get_tenant_id(request)
#     owner = db.query(ClientDetail).filter(
#         ClientDetail.claim_id == claim_id,
#         ClientDetail.tenant_id == tenant_id,
#         ClientDetail.role == role
#     ).first()
#     if not owner:
#         raise HTTPException(status_code=404, detail="Vehicle Owner not found")
#     return owner


# def update_vehicle_owner_service(claim_id: int, request: Request, owner_data: VehicleOwnerIn, db: Session, role: PersonRoleEnum):
#     tenant_id = get_tenant_id(request)
#     current_user_id = actor_id(request)
#     db_owner = db.query(ClientDetail).filter(
#         ClientDetail.claim_id == claim_id,
#         ClientDetail.tenant_id == tenant_id,
#         ClientDetail.role == role
#     ).first()

#     if not db_owner:
#         raise HTTPException(status_code=404, detail="Vehicle Owner not found")

#     field_label_map = {
#         "first_name": "First Name",
#         "surname": "Surname",
#         "payment_benificiary": "Vehicle Payment Beneficiary",

#         # Address (nested)
#         "address.address": "Address",
#         "address.postcode": "Postcode",
#         "address.home_tel": "Home Telephone",
#         "address.mobile_tel": "Mobile Telephone",
#         "address.email": "Email",

#         # Insurer update
#         "policy_holder": "Policy Holder"
#     }

#     changed_fields = []

#     # ✅ Track primitive field changes
#     for key, new_value in owner_data.dict(exclude={"address"}).items():
#         old_value = getattr(db_owner, key)
#         if new_value is not None and new_value != old_value:
#             changed_fields.append(key)
#             setattr(db_owner, key, new_value)

#     # ✅ Track address changes
#     if owner_data.address:
#         if db_owner.address:
#             for key, new_value in owner_data.address.dict().items():
#                 old_value = getattr(db_owner.address, key)
#                 if new_value is not None and new_value != old_value:
#                     changed_fields.append(f"address.{key}")
#                     setattr(db_owner.address, key, new_value)
#         else:
#             db_owner.address = Address(**owner_data.address.dict())
#             changed_fields.append("address")

#     # ✅ Insurer consistency
#     insurer = db.query(InsurerBroker).filter(
#         InsurerBroker.claim_id == claim_id,
#         InsurerBroker.tenant_id == tenant_id
#     ).first()

#     full_name = f"{db_owner.first_name} {db_owner.surname}".strip()
#     if insurer:
#         policy_holder_name = insurer.policy_holder or ""
#         if policy_holder_name.strip().lower() != full_name.lower():
#             insurer.policy_holder = full_name
#             db.add(insurer)
#             changed_fields.append("policy_holder")

#     # ✅ Convert to friendly labels
#     readable_changes = []
#     for c in changed_fields:
#         readable_changes.append(field_label_map.get(c, c))

#     # ✅ Create history activity
#     if readable_changes:
#         file_path = ", ".join(readable_changes)
#         reference = build_case_reference(claim_id,db)
#         HistoryActivityService.create_activity(
#             db=db,
#             claim_id=claim_id,
#             file_name=f"The vehicle owner detail has been updated for claim {reference}",
#             file_path=file_path,
#             file_type=HistoryLogType.UPDATED_VEHICLE_OWNER,
#             user_id=current_user_id,
#             tenant_id=tenant_id
#         )
#     db_owner.updated_by=current_user_id
#     db.commit()
#     db.refresh(db_owner)
#     return db_owner


# def deactivate_vehicle_owner_service(claim_id: int, request: Request, db: Session, role: PersonRoleEnum):
#     tenant_id = get_tenant_id(request)
#     db_owner = db.query(ClientDetail).filter(
#         ClientDetail.claim_id == claim_id,
#         ClientDetail.tenant_id == tenant_id,
#         ClientDetail.role == role
#     ).first()

#     if not db_owner:
#         raise HTTPException(status_code=404, detail="Vehicle Owner not found")

#     db_owner.is_active = False
#     db.commit()
#     db.refresh(db_owner)
#     return {"detail": "Vehicle Owner deactivated successfully"}
