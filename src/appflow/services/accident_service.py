# appflow/services/accident_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status,Request

from libdata.models.tables import LocationCondition,Claim
from appflow.models.accident_detail import AccidentDetailIn, AccidentDetailOut,AccidentDisplayLabels

from appflow.models.passenger import PassengerIn
from appflow.utils import get_tenant_id,actor_id,build_case_reference
from libdata.enums import PersonRoleEnum,HistoryLogType
from libdata.models.tables import ClientDetail, Address, PoliceDetail
from appflow.models.police_detail import PoliceDetailIn
from appflow.services.history_activity_service import HistoryActivityService


class AccidentService:
    @staticmethod
    def create_location_condition(
        db: Session, accident_data: AccidentDetailIn, tenant_id: int,current_user_id
    ) -> LocationCondition:
        claim = db.query(Claim).filter(
            Claim.id == accident_data.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        """Create a new location condition"""
        data_dict = accident_data.dict()
        data_dict['tenant_id'] = tenant_id
        data_dict['created_by'] = current_user_id
        data_dict['updated_by'] = current_user_id
        obj = LocationCondition(**data_dict)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        reference = build_case_reference(claim.id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=obj.claim_id,
            file_name=f"The accident detail has been created for claim {reference}",
            file_path="",
            file_type=HistoryLogType.CREATED_ACCIDENT_DETAIL,
            user_id=current_user_id,
            tenant_id=tenant_id
        )
        return obj

    @staticmethod
    def get_all_location_conditions(
        db: Session, claim_id: Optional[int] = None
    ) -> List[LocationCondition]:
        """Get all location conditions, optionally filtered by claim_id"""
        query = db.query(LocationCondition)
        if claim_id:
            query = query.filter(LocationCondition.claim_id == claim_id)
        return query.all()

    @staticmethod
    def get_location_condition_by_id(
        db: Session, id: int
    ) -> LocationCondition:
        """Get a specific location condition by ID"""
        obj = db.query(LocationCondition).filter(LocationCondition.id == id).first()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LocationCondition not found"
            )
        return obj

    @staticmethod
    def get_location_condition_by_claim(db: Session, claim_id: int) -> AccidentDetailOut:
        obj = db.query(LocationCondition).filter(LocationCondition.claim_id == claim_id).first()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LocationCondition not found"
            )
        return obj


    @staticmethod
    def update_location_condition(
        db: Session, claim_id: int, data: AccidentDetailIn,tenant_id: int, actor_id: int
    ) -> LocationCondition:
        claim = db.query(Claim).filter(
            Claim.id == data.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        """Update an existing location condition"""
        obj = db.query(LocationCondition).filter(LocationCondition.claim_id == claim_id).first()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LocationCondition not found"
            )

        changed_fields = []
        for key, value in data.dict().items():
            old_value = getattr(obj, key)

            if old_value != value:
                setattr(obj, key, value)

                label = AccidentDisplayLabels.format(key)
                changed_fields.append(label)

        obj.updated_by=actor_id
        db.commit()
        db.refresh(obj)
        reference = build_case_reference(claim.id,db)
        if changed_fields:
            HistoryActivityService.create_activity(
                db=db,
                claim_id=obj.claim_id,
                file_name=f"The accident detail has been updated for claim {reference}",
                file_path=", ".join(changed_fields),
                file_type=HistoryLogType.UPDATED_ACCIDENT_DETAIL,
                user_id=actor_id,
                tenant_id=tenant_id
            )
        return obj

    @staticmethod
    def deactivate_location_condition(
        db: Session, id: int
    ) -> LocationCondition:
        """Deactivate a location condition"""
        obj = db.query(LocationCondition).filter(LocationCondition.id == id).first()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LocationCondition not found"
            )

        obj.is_active = False
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def create_passenger(request: Request, payload: PassengerIn, db: Session):
        tenant_id = get_tenant_id(request)
        current_user_id = actor_id(request)
        claim = db.query(Claim).filter(
            Claim.id == payload.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        # 1. Handle Address (if provided)
        address_id = None
        if payload.address:
            db_address = Address(**payload.address.dict())
            db.add(db_address)
            db.flush()
            db.refresh(db_address)
            address_id = db_address.id

        # 2. Create Passenger as ClientDetail
        db_passenger = ClientDetail(
            gender=payload.gender,
            first_name=payload.first_name,
            surname=payload.surname,
            tenant_id=tenant_id,
            claim_id=payload.claim_id,
            address_id=address_id,
            role=PersonRoleEnum.PASSENGER.value,
            created_by=current_user_id,
            updated_by=current_user_id
        )
        db.add(db_passenger)
        db.commit()
        db.refresh(db_passenger)
        reference = build_case_reference(claim.id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=db_passenger.claim_id,
            file_name=f"The passenger has been created for claim {reference}",
            file_path="",
            file_type=HistoryLogType.CREATED_PASSENGER_DETAIL,
            user_id=current_user_id,
            tenant_id=tenant_id
        )

        return db_passenger

    @staticmethod
    def get_passengers_by_claim_id(claim_id: int, db: Session):
        return db.query(ClientDetail).filter(
            ClientDetail.claim_id == claim_id,
            ClientDetail.role == "PASSENGER",
            ClientDetail.is_active == True
        ).all()

    @staticmethod
    def get_passenger_by_id(id: int, db: Session):
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "PASSENGER",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Passenger not found or inactive")

        return db_obj

    @staticmethod
    def update_passenger(id: int, payload, db: Session,current_user: int, tenant_id: int):
        claim = db.query(Claim).filter(
            Claim.id == payload.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        FIELD_LABELS = {
            "first_name": "First Name",
            "surname": "Surname",
        }
        ADDRESS_FIELD_LABELS = {
            "line1": "Address",
            "postcode": "Postcode",
            "mobile_tel": "Mobile Number",
        }
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "PASSENGER",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Passenger not found or inactive")

        update_data = payload.dict(exclude_unset=True)

        changed_fields = []

        # Address handling
        if "address" in update_data and update_data["address"] is not None:
            address_data = update_data.pop("address")
            if db_obj.address:
                for key, value in address_data.items():
                    old = getattr(db_obj.address, key)
                    if old != value:
                        setattr(db_obj.address, key, value)
                        changed_fields.append(ADDRESS_FIELD_LABELS.get(key, key.title()))
            else:
                new_addr = Address(**address_data)
                db.add(new_addr)
                db.flush()
                db_obj.address_id = new_addr.id
                changed_fields.append("Address Added")

        # Scalars
        for key, value in update_data.items():
            old = getattr(db_obj, key)
            if old != value:
                setattr(db_obj, key, value)
                changed_fields.append(FIELD_LABELS.get(key, key.replace("_", " ").title()))
        db_obj.updated_by=current_user
        db.commit()
        db.refresh(db_obj)
        reference = build_case_reference(claim.id,db)
        if changed_fields:
            HistoryActivityService.create_activity(
                db=db,
                claim_id=db_obj.claim_id,
                file_name=f"The passenger has been updated for claim {reference}",
                file_path=", ".join(changed_fields),
                file_type=HistoryLogType.UPDATED_PASSENGER_DETAIL,
                user_id=current_user,
                tenant_id=tenant_id
            )
        return db_obj

    @staticmethod
    def deactivate_passenger(id: int, db: Session,actor_id):
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "PASSENGER",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Passenger not found or already inactive")
        claim = db.query(Claim).filter(
            Claim.id == db_obj.claim_id,
            Claim.tenant_id == db_obj.tenant_id
        ).first()

        db_obj.updated_by=actor_id
        db_obj.is_active = False
        db.commit()
        reference = build_case_reference(claim.id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=db_obj.claim_id,
            file_name=f"The passenger has been deactivated for claim {reference}",
            file_path="",
            file_type=HistoryLogType.DEACTIVATED_PASSENGER_DETAIL,
            user_id=actor_id,
            tenant_id=db_obj.tenant_id
        )
        return {"message": "Passenger deactivated successfully"}

    @staticmethod
    def create_witness(request, payload, db):
        tenant_id = get_tenant_id(request)
        current_user = actor_id(request)
        claim = db.query(Claim).filter(
            Claim.id == payload.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        address_id = None
        if payload.address:
            db_address = Address(**payload.address.dict())
            db.add(db_address)
            db.flush()
            db.refresh(db_address)
            address_id = db_address.id

        db_witness = ClientDetail(
            gender=payload.gender,
            first_name=payload.first_name,
            surname=payload.surname,
            tenant_id=tenant_id,
            claim_id=payload.claim_id,
            address_id=address_id,
            witness_independent=payload.witness_independent,
            role=PersonRoleEnum.WITNESS.value,
            created_by=current_user,
            updated_by=current_user
        )
        db.add(db_witness)
        db.commit()
        db.refresh(db_witness)
        reference = build_case_reference(claim.id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=payload.claim_id,
            file_name=f"The witness has been created for claim {reference}",
            file_path="",
            file_type=HistoryLogType.CREATED_WITNESS_DETAIL,
            user_id=current_user,
            tenant_id=tenant_id,
        )
        return db_witness

    @staticmethod
    def get_witness_by_claim_id(claim_id: int, db: Session):
        return db.query(ClientDetail).filter(
            ClientDetail.claim_id == claim_id,
            ClientDetail.role == "WITNESS",
            ClientDetail.is_active == True
        ).all()

    @staticmethod
    def get_witness_by_id(id: int, db: Session):
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "WITNESS",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Witness not found or inactive")

        return db_obj

    @staticmethod
    def update_witness_detail(id: int, payload, db: Session, tenant_id: int,current_user: int):
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "WITNESS",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Witness not found or inactive")
        claim = db.query(Claim).filter(
            Claim.id == payload.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        update_data = payload.dict(exclude_unset=True)

        changed_fields = []
        field_label_map = {
            "first_name": "First Name",
            "surname": "Surname",
            "address": "Address",
            "postcode": "Postcode",
            "mobile_tel": "Mobile Number",
            "email": "Email",
        }

        # ✅ ADDRESS HANDLING
        if "address" in update_data and update_data["address"] is not None:
            address_data = update_data.pop("address")
            if db_obj.address:
                for key, value in address_data.items():
                    old_value = getattr(db_obj.address, key)
                    if old_value != value:
                        setattr(db_obj.address, key, value)
                        label = field_label_map.get(key, f"Address {key.replace('_', ' ').title()}")
                        changed_fields.append(label)
            else:
                new_address = Address(**address_data)
                db.add(new_address)
                db.flush()
                db_obj.address_id = new_address.id
                changed_fields.append("Address Added")

        # ✅ NORMAL FIELDS
        for key, value in update_data.items():
            old_value = getattr(db_obj, key)
            if old_value != value:
                setattr(db_obj, key, value)
                label = field_label_map.get(key, key.replace("_", " ").title())
                changed_fields.append(label)
        db_obj.updated_by=current_user
        db.commit()
        db.refresh(db_obj)
        reference = build_case_reference(claim.id,db)
        if changed_fields:
            HistoryActivityService.create_activity(
                db=db,
                claim_id=db_obj.claim_id,
                file_name=f"The witness has been updated for claim {reference}",
                file_path=", ".join(changed_fields),
                file_type=HistoryLogType.UPDATED_WITNESS_DETAIL,
                user_id=current_user,
                tenant_id=tenant_id,
            )
        return db_obj

    @staticmethod
    def deactivate_witness_detail(id: int, db: Session, tenant_id: int, current_user: int):
        db_obj = db.query(ClientDetail).filter(ClientDetail.id == id).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Witness not found or already inactive")
        claim = db.query(Claim).filter(
            Claim.id == db_obj.claim_id,
            Claim.tenant_id == tenant_id
        ).first()

        db_obj.updated_by=current_user
        db_obj.is_active = False
        db.commit()
        reference = build_case_reference(claim.id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=db_obj.claim_id,
            file_name=f"The witness has been deactivated for claim {reference}",
            file_path="",
            file_type=HistoryLogType.DEACTIVATED_WITNESS_DETAIL,
            user_id=current_user,
            tenant_id=tenant_id
        )
        return {"message": "witness deactivated successfully"}

    @staticmethod
    def create_police_detail(request: Request, payload: PoliceDetailIn, db: Session):
        tenant_id = get_tenant_id(request)
        current_user = actor_id(request)
        claim = db.query(Claim).filter(
            Claim.id == payload.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        db_police = PoliceDetail(
            claim_id=payload.claim_id,
            name=payload.name,
            reference_no=payload.reference_no,
            station_name=payload.station_name,
            station_address=payload.station_address,
            incident_report_taken=payload.incident_report_taken,
            report_received_date=payload.report_received_date,
            additional_info=payload.additional_info,
            created_by=current_user,
            updated_by=current_user
        )
        db.add(db_police)
        db.commit()
        reference = build_case_reference(claim.id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=payload.claim_id,
            file_name=f"The police detail has been created for claim {reference}",
            file_path="",
            file_type=HistoryLogType.CREATED_POLICE_DETAIL,
            user_id=current_user,
            tenant_id=tenant_id,
        )
        db.refresh(db_police)
        return db_police

    @staticmethod
    def get_police_by_claim_id(claim_id: int, db: Session):
        return db.query(PoliceDetail).filter(
            PoliceDetail.claim_id == claim_id,
            PoliceDetail.is_active == True
        ).all()

    @staticmethod
    def update_police_detail(id: int, payload, db: Session, request):
        tenant_id = get_tenant_id(request)
        actor = actor_id(request)
        claim = db.query(Claim).filter(
            Claim.id == payload.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        db_obj = db.query(PoliceDetail).filter(
            PoliceDetail.id == id,
            PoliceDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Police detail not found or inactive")

        update_data = payload.dict(exclude_unset=True)
        changed_fields = []

        # ✅ Friendly labels
        field_label_map = {
            "name": "Police Constable Name",
            "reference_no": "Reference No.",
            "station_name": "Police Station Name",
            "station_address": "Police Station Address",
            "incident_report_taken": "Incident Report Taken?",
            "report_received_date": "Report Received Date",
            "additional_info": "Note/Additional Information",
        }

        update_data = payload.dict(exclude_unset=True, exclude={"claim_id"})
        changed_fields = []

        for key, value in update_data.items():
            old_value = getattr(db_obj, key, None)
            if old_value != value:
                setattr(db_obj, key, value)
                label = field_label_map.get(
                    key,
                    key.replace("_", " ").title()
                )
                changed_fields.append(label)

        db_obj.updated_by=actor
        db.commit()
        db.refresh(db_obj)
        reference = build_case_reference(claim.id,db)
        if changed_fields:
            HistoryActivityService.create_activity(
                db=db,
                claim_id=db_obj.claim_id,
                file_name=f"The police details has been updated for claim {reference}",
                file_path=", ".join(changed_fields),
                file_type=HistoryLogType.UPDATED_POLICE_DETAIL,
                user_id=actor,
                tenant_id=tenant_id
            )
        return db_obj

    @staticmethod
    def get_police_by_id(id: int, db: Session):
        db_obj = db.query(PoliceDetail).filter(
            PoliceDetail.id == id,
            PoliceDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Police detail not found or inactive")

        return db_obj

    @staticmethod
    def deactivate_police_detail(id: int, db: Session, request):
        tenant_id = get_tenant_id(request)
        actor = actor_id(request)
        db_obj = db.query(PoliceDetail).filter(PoliceDetail.id == id).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Police detail not found")
        claim = db.query(Claim).filter(
            Claim.id == db_obj.claim_id,
            Claim.tenant_id == tenant_id
        ).first()

        db_obj.updated_by=actor
        db_obj.is_active = False
        db.commit()
        reference = build_case_reference(claim.id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=db_obj.claim_id,
            file_name=f"The police detail has been deactivated for claim {reference}",
            file_path="",
            file_type=HistoryLogType.DEACTIVATED_POLICE_DETAIL,
            user_id=actor,
            tenant_id=tenant_id
        )
        return {"message": "Police detail deactivated successfully"}