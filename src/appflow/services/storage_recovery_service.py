from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from libdata.models.tables import Storage, Recovery, Address, Claim
from appflow.models.storage_recovery import StorageRecoveryIn, StorageRecoveryOut,StorageRecoveryUpdateOut,StorageRecoveryUpdateIn,StorageOut,RecoveryOut
from datetime import date
from appflow.utils import actor_id,build_case_reference
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType


class StorageRecoveryService:

    @staticmethod
    def create_storage_recovery(payload: StorageRecoveryIn, db: Session, tenant_id: int,user_id: int):
        # Determine claim_id from storages or recoveries
        claim_id = None
        if payload.storages:
            claim_id = payload.storages[0].claim_id
        elif payload.recoveries:
            claim_id = payload.recoveries[0].claim_id

        claim = db.query(Claim).filter(
            Claim.id == claim_id,
            # Claim.tenant_id == tenant_id,
        ).first()

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        try:
            created_storages = []
            created_recoveries = []

            # ---- Storages ----
            for storage in payload.storages:
                storage_data = storage.dict()
                address_data = storage_data.pop("address", None)
                storage_data.pop("id", None)  # let the DB assign the integer PK

                address = None
                if address_data:
                    address = Address(**address_data,created_by=user_id,updated_by=user_id)
                    db.add(address)
                    db.flush()
                    storage_data["address_id"] = address.id

                new_storage = Storage(**storage_data,created_by=user_id,updated_by=user_id)
                db.add(new_storage)
                db.flush()
                created_storages.append(new_storage)

            # ---- Recoveries ----
            for recovery in payload.recoveries:
                recovery_data = recovery.dict()
                address_data = recovery_data.pop("address", None)
                recovery_data.pop("id", None)  # let the DB assign the integer PK

                address = None
                if address_data:
                    address = Address(**address_data,created_by=user_id,updated_by=user_id)
                    db.add(address)
                    db.flush()
                    recovery_data["address_id"] = address.id

                new_recovery = Recovery(**recovery_data,created_by=user_id,updated_by=user_id)
                db.add(new_recovery)
                db.flush()
                created_recoveries.append(new_recovery)

            db.commit()
            reference = build_case_reference(claim.id,db)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim.id,
                file_name=f"The storage & recovery has been created for claim {reference}",
                file_path="",
                file_type=HistoryLogType.CREATED_STORAGE_RECOVERY,
                user_id=user_id,
                tenant_id=tenant_id
            )

            return StorageRecoveryOut(
                storages=[StorageOut.from_orm(s) for s in created_storages],
                recoveries=[RecoveryOut.from_orm(r) for r in created_recoveries],
            )

        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Error creating storage/recovery: {str(e)}",
            )

    @staticmethod
    def get_storage_recovery_by_claim(claim_id: int, db: Session, tenant_id: int):
        claim = (
            db.query(Claim)
            .options(
                joinedload(Claim.storages.and_(Storage.is_active==True,Storage.is_deleted==False)).joinedload(Storage.address),
                joinedload(Claim.recoveries.and_(Recovery.is_active==True,Recovery.is_deleted==False)).joinedload(Recovery.address),
            )
            .filter(Claim.id == claim_id, 
                    # Claim.tenant_id == tenant_id
            ).first()
        )

        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        return StorageRecoveryOut(
            storages=claim.storages,
            recoveries=claim.recoveries,
        )

    @staticmethod
    def update_storage_recovery_by_claim(
            claim_id: int,
            payload: StorageRecoveryUpdateIn,
            db: Session,
            tenant_id: int,
            current_user_id: int
    ):
        claim = (
            db.query(Claim)
            .options(
                joinedload(Claim.storages.and_(Storage.is_active == True, Storage.is_deleted == False)).joinedload(
                    Storage.address),
                joinedload(Claim.recoveries.and_(Recovery.is_active == True, Recovery.is_deleted == False)).joinedload(
                    Recovery.address),
            )
            .filter(
                Claim.id == claim_id,
                # Claim.tenant_id == tenant_id
            )
            .first()
        )

        if not claim:
            raise HTTPException(404, "Claim not found")

        # Field label maps for human-readable field names
        storage_field_map = {
            "storage_provider": "Storage Provider",
            "name": "Name",
            "start_date": "Storage Start Date",
            "end_date": "Storage End Date",
            "total_storage_days": "Total Storage Days",
            "currency": "Storage Currency",
            "charge_per_day": "Charge Per Day",
            "total_storage_charges": "Total Storage Charges",
        }

        recovery_field_map = {
            "recovery_provider": "Recovery Provider",
            "name": "Name",
            "date_of_recovery": "Date of Recovery",
            "currency": "Recovery Currency",
            "recovery_charges": "Recovery Charges",
        }

        address_field_map = {
            "address": "Address",
            "postcode": "Postcode",
            "mobile_tel": "Telephone Main",
            "email": "Email",
        }

        updated_fields = []

        try:
            # -------------------------------------------------------
            # 🔵 HANDLE STORAGES
            # -------------------------------------------------------
            existing_storages = {
                s.id: s for s in claim.storages
                if s.is_active and not s.is_deleted
            }

            incoming_ids = set()

            for storage_payload in (payload.storages or []):
                if storage_payload.id and storage_payload.id in existing_storages:  # ------- UPDATE EXISTING --------
                    incoming_ids.add(storage_payload.id)

                    db_record = existing_storages[storage_payload.id]
                    storage_data = storage_payload.dict(exclude={"address"})
                    address_data = storage_payload.address

                    # --- Update storage fields ---
                    for key, value in storage_data.items():
                        if key == "claim_id" or value is None:
                            continue

                        old_value = getattr(db_record, key)
                        if old_value != value:
                            # Add human-readable field name
                            field_name = storage_field_map.get(key, key.replace('_', ' ').title())
                            updated_fields.append(f"Storage: {field_name}")
                            setattr(db_record, key, value)
                            db_record.updated_by = current_user_id

                    # --- Update address ---
                    if address_data:
                        if db_record.address:
                            for k, v in address_data.model_dump().items():
                                if v is None:
                                    continue

                                old_value = getattr(db_record.address, k)
                                if old_value != v:
                                    # Add human-readable address field name
                                    field_name = address_field_map.get(k, k.replace('_', ' ').title())
                                    updated_fields.append(f"Storage: {field_name}")
                                    setattr(db_record.address, k, v)
                                    db_record.address.updated_by = current_user_id
                        else:
                            new_addr = Address(
                                **address_data.model_dump(exclude_unset=True),
                                created_by=current_user_id,
                                updated_by=current_user_id
                            )
                            db.add(new_addr)
                            db.flush()
                            db_record.address_id = new_addr.id
                            updated_fields.append("Storage: Address (new)")

                else:  # ------- CREATE NEW --------
                    # Drop any client-generated temp id (the frontend uses
                    # Date.now(), which overflows the integer PK) — let the DB
                    # assign the real id.
                    storage_data = storage_payload.dict(exclude={"address", "id"})
                    address_data = storage_payload.address

                    if address_data:
                        new_addr = Address(
                            **address_data.model_dump(exclude_unset=True),
                            created_by=current_user_id,
                            updated_by=current_user_id
                        )
                        db.add(new_addr)
                        db.flush()
                        storage_data["address_id"] = new_addr.id

                    storage_data.pop("claim_id", None)
                    new_storage = Storage(
                        **storage_data,
                        claim_id=claim.id,
                        created_by=current_user_id,
                        updated_by=current_user_id
                    )
                    db.add(new_storage)
                    updated_fields.append("Storage: New Storage Created")

            # Soft delete missing storages
            for s_id, db_record in existing_storages.items():
                if s_id not in incoming_ids:
                    db_record.is_active = False
                    db_record.is_deleted = True
                    db_record.updated_by = current_user_id
                    updated_fields.append("Storage: Storage Deleted")

            # -------------------------------------------------------
            # 🔵 HANDLE RECOVERIES (Same Logic)
            # -------------------------------------------------------
            existing_recoveries = {
                r.id: r for r in claim.recoveries
                if r.is_active and not r.is_deleted
            }

            incoming_ids_rec = set()

            for recovery_payload in (payload.recoveries or []):
                if recovery_payload.id and recovery_payload.id in existing_recoveries:  # ------- UPDATE EXISTING --------
                    incoming_ids_rec.add(recovery_payload.id)

                    db_record = existing_recoveries[recovery_payload.id]
                    recovery_data = recovery_payload.dict(exclude={"address"})
                    address_data = recovery_payload.address

                    for key, value in recovery_data.items():
                        if key == "claim_id" or value is None:
                            continue

                        old_value = getattr(db_record, key)
                        if old_value != value:
                            # Add human-readable field name
                            field_name = recovery_field_map.get(key, key.replace('_', ' ').title())
                            updated_fields.append(f"Recovery: {field_name}")
                            setattr(db_record, key, value)
                            db_record.updated_by = current_user_id

                    if address_data:
                        if db_record.address:
                            for k, v in address_data.model_dump().items():
                                if v is None:
                                    continue

                                old_value = getattr(db_record.address, k)
                                if old_value != v:
                                    # Add human-readable address field name
                                    field_name = address_field_map.get(k, k.replace('_', ' ').title())
                                    updated_fields.append(f"Recovery: {field_name}")
                                    setattr(db_record.address, k, v)
                                    db_record.address.updated_by = current_user_id
                        else:
                            new_addr = Address(
                                **address_data.model_dump(exclude_unset=True),
                                created_by=current_user_id,
                                updated_by=current_user_id
                            )
                            db.add(new_addr)
                            db.flush()
                            db_record.address_id = new_addr.id
                            updated_fields.append("Recovery: Address (new)")

                else:  # ------- CREATE NEW --------
                    # Drop any client-generated temp id (see storage note above).
                    recovery_data = recovery_payload.dict(exclude={"address", "id"})
                    address_data = recovery_payload.address

                    if address_data:
                        new_addr = Address(
                            **address_data.model_dump(exclude_unset=True),
                            created_by=current_user_id,
                            updated_by=current_user_id
                        )
                        db.add(new_addr)
                        db.flush()
                        recovery_data["address_id"] = new_addr.id

                    recovery_data.pop("claim_id", None)
                    new_recovery = Recovery(
                        **recovery_data,
                        claim_id=claim.id,
                        created_by=current_user_id,
                        updated_by=current_user_id
                    )
                    db.add(new_recovery)
                    updated_fields.append("Recovery: New Recovery Created")

            # Soft delete missing recoveries
            for r_id, db_record in existing_recoveries.items():
                if r_id not in incoming_ids_rec:
                    db_record.is_active = False
                    db_record.is_deleted = True
                    db_record.updated_by = current_user_id
                    updated_fields.append("Recovery: Recovery Deleted")

            db.commit()
            db.refresh(claim)

            # Create history log
            reference = build_case_reference(claim.id, db)
            if updated_fields:
                # Remove duplicates while preserving order
                unique_fields = []
                seen = set()
                for field in updated_fields:
                    if field not in seen:
                        seen.add(field)
                        unique_fields.append(field)

                HistoryActivityService.create_activity(
                    db=db,
                    claim_id=claim.id,
                    file_name=f"The storage & recovery details updated for claim {reference}",
                    file_path=", ".join(unique_fields),
                    file_type=HistoryLogType.UPDATED_STORAGE_RECOVERY,
                    user_id=current_user_id,
                    tenant_id=tenant_id,
                )

            return StorageRecoveryOut(
                storages=claim.storages,
                recoveries=claim.recoveries,
            )

        except Exception as e:
            db.rollback()
            raise HTTPException(500, f"Error updating storage/recovery: {str(e)}")
    # @staticmethod
    # def update_storage_recovery_by_claim(
    #         claim_id: int,
    #         payload: StorageRecoveryUpdateIn,
    #         db: Session,
    #         tenant_id: int,
    #         current_user_id: int
    # ):
    #     claim = (
    #         db.query(Claim)
    #         .options(
    #             joinedload(Claim.storages.and_(Storage.is_active==True,Storage.is_deleted==False)).joinedload(Storage.address),
    #             joinedload(Claim.recoveries.and_(Recovery.is_active==True,Recovery.is_deleted==False)).joinedload(Recovery.address),
    #         )
    #         .filter(
    #             Claim.id == claim_id,
    #             # Claim.tenant_id == tenant_id
    #         )
    #         .first()
    #     )
    #
    #     if not claim:
    #         raise HTTPException(404, "Claim not found")
    #
    #     updated_fields = []
    #
    #     try:
    #         # -------------------------------------------------------
    #         # 🔵 HANDLE STORAGES
    #         # -------------------------------------------------------
    #         existing_storages = {
    #             s.id: s for s in claim.storages
    #             if s.is_active and not s.is_deleted
    #         }
    #
    #         incoming_ids = set()
    #
    #         for storage_payload in (payload.storages or []):
    #             if storage_payload.id:  # ------- UPDATE EXISTING --------
    #                 incoming_ids.add(storage_payload.id)
    #                 if storage_payload.id not in existing_storages:
    #                     continue
    #
    #                 db_record = existing_storages[storage_payload.id]
    #                 storage_data = storage_payload.dict(exclude={"address"})
    #                 address_data = storage_payload.address
    #
    #                 # --- Update storage fields ---
    #                 for key, value in storage_data.items():
    #                     old_value = getattr(db_record, key)
    #                     if old_value != value:
    #                         setattr(db_record, key, value)
    #                         db_record.updated_by = current_user_id
    #                         updated_fields.append(key)
    #
    #                 # --- Update address ---
    #                 if address_data:
    #                     if db_record.address:
    #                         for k, v in address_data.model_dump().items():
    #                             old_value = getattr(db_record.address, k)
    #                             if old_value != v:
    #                                 setattr(db_record.address, k, v)
    #                                 updated_fields.append(k)
    #                     else:
    #                         new_addr = Address(
    #                             **address_data.dict(),
    #                             created_by=current_user_id,
    #                             updated_by=current_user_id
    #                         )
    #                         db.add(new_addr)
    #                         db.flush()
    #                         db_record.address_id = new_addr.id
    #
    #             else:  # ------- CREATE NEW --------
    #                 storage_data = storage_payload.dict(exclude={"address"})
    #                 address_data = storage_payload.address
    #
    #                 if address_data:
    #                     new_addr = Address(
    #                         **address_data.dict(),
    #                         created_by=current_user_id,
    #                         updated_by=current_user_id
    #                     )
    #                     db.add(new_addr)
    #                     db.flush()
    #                     storage_data["address_id"] = new_addr.id
    #
    #                 storage_data.pop("claim_id", None)
    #                 new_storage = Storage(
    #                     **storage_data,
    #                     claim_id=claim.id,
    #                     created_by=current_user_id,
    #                     updated_by=current_user_id
    #                 )
    #                 db.add(new_storage)
    #                 updated_fields.append("New Storage Created")
    #
    #         # Soft delete missing storages
    #         for s_id, db_record in existing_storages.items():
    #             if s_id not in incoming_ids:
    #                 db_record.is_active = False
    #                 db_record.is_deleted = True
    #                 db_record.updated_by = current_user_id
    #                 updated_fields.append("Storage Deleted")
    #
    #         # -------------------------------------------------------
    #         # 🔵 HANDLE RECOVERIES (Same Logic)
    #         # -------------------------------------------------------
    #         existing_recoveries = {
    #             r.id: r for r in claim.recoveries
    #             if r.is_active and not r.is_deleted
    #         }
    #
    #         incoming_ids_rec = set()
    #
    #         for recovery_payload in (payload.recoveries or []):
    #             if recovery_payload.id:  # ------- UPDATE EXISTING --------
    #                 incoming_ids_rec.add(recovery_payload.id)
    #
    #                 if recovery_payload.id not in existing_recoveries:
    #                     continue
    #
    #                 db_record = existing_recoveries[recovery_payload.id]
    #                 recovery_data = recovery_payload.dict(exclude={"address"})
    #                 address_data = recovery_payload.address
    #
    #                 for key, value in recovery_data.items():
    #                     old_value = getattr(db_record, key)
    #                     if old_value != value:
    #                         setattr(db_record, key, value)
    #                         db_record.updated_by = current_user_id
    #                         updated_fields.append(key)
    #
    #                 if address_data:
    #                     if db_record.address:
    #                         for k, v in address_data.model_dump().items():
    #                             old_value = getattr(db_record.address, k)
    #                             if old_value != v:
    #                                 setattr(db_record.address, k, v)
    #                                 updated_fields.append(k)
    #                     else:
    #                         new_addr = Address(
    #                             **address_data.dict(),
    #                             created_by=current_user_id,
    #                             updated_by=current_user_id
    #                         )
    #                         db.add(new_addr)
    #                         db.flush()
    #                         db_record.address_id = new_addr.id
    #
    #             else:  # ------- CREATE NEW --------
    #                 recovery_data = recovery_payload.dict(exclude={"address"})
    #                 address_data = recovery_payload.address
    #
    #                 if address_data:
    #                     new_addr = Address(
    #                         **address_data.model_dump(),
    #                         created_by=current_user_id,
    #                         updated_by=current_user_id
    #                     )
    #                     db.add(new_addr)
    #                     db.flush()
    #                     recovery_data["address_id"] = new_addr.id
    #
    #                 recovery_data.pop("claim_id", None)
    #                 new_recovery = Recovery(
    #                     **recovery_data,
    #                     claim_id=claim.id,
    #                     created_by=current_user_id,
    #                     updated_by=current_user_id
    #                 )
    #                 db.add(new_recovery)
    #                 updated_fields.append("New Recovery Created")
    #
    #         # Soft delete missing recoveries
    #         for r_id, db_record in existing_recoveries.items():
    #             if r_id not in incoming_ids_rec:
    #                 db_record.is_active = False
    #                 db_record.is_deleted = True
    #                 db_record.updated_by = current_user_id
    #                 updated_fields.append("Recovery Deleted")
    #
    #         db.commit()
    #         db.refresh(claim)
    #
    #         # Create history log
    #         reference = build_case_reference(claim.id, db)
    #         if updated_fields and current_user_id:
    #             HistoryActivityService.create_activity(
    #                 db=db,
    #                 claim_id=claim.id,
    #                 file_name=f"The storage & recovery details updated for claim {reference}",
    #                 file_path=", ".join(sorted(set(updated_fields))),
    #                 file_type=HistoryLogType.UPDATED_STORAGE_RECOVERY,
    #                 user_id=current_user_id,
    #                 tenant_id=tenant_id,
    #             )
    #
    #         return StorageRecoveryOut(
    #             storages=claim.storages,
    #             recoveries=claim.recoveries,
    #         )
    #
    #     except Exception as e:
    #         db.rollback()
    #         raise HTTPException(500, f"Error updating storage/recovery: {str(e)}")

    @staticmethod
    def search_storage(query: str, db: Session, tenant_id: int):
        return (
            db.query(Storage)
            .options(joinedload(Storage.address))
            .join(Claim)
            .filter(
                Storage.storage_provider.ilike(f"%{query}%"),  # search by storage name
                # # Claim.tenant_id == tenant_id
            )
            .all()
        )

    @staticmethod
    def search_recovery(query: str, db: Session, tenant_id: int):
        return (
            db.query(Recovery)
            .options(joinedload(Recovery.address))
            .join(Claim)
            .filter(
                Recovery.recovery_provider.ilike(f"%{query}%"),  # search by recovery name
                # Claim.tenant_id == tenant_id
            )
            .all()
        )