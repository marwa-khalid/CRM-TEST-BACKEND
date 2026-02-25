# appflow/services/accident_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status,Request

from libdata.models.tables import LocationCondition
from appflow.models.accident_detail import AccidentDetailIn, AccidentDetailOut

from appflow.models.passenger import PassengerIn
from appflow.utils import get_tenant_id
from libdata.enums import PersonRoleEnum
from libdata.models.tables import ClientDetail, Address, PoliceDetail
from appflow.models.police_detail import PoliceDetailIn


class AccidentService:
    @staticmethod
    def create_location_condition(
        db: Session, accident_data: AccidentDetailIn, tenant_id: str
    ) -> LocationCondition:
        """Create a new location condition"""
        data_dict = accident_data.dict()
        data_dict['tenant_id'] = tenant_id
        obj = LocationCondition(**data_dict)
        db.add(obj)
        db.commit()
        db.refresh(obj)
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
        db: Session, claim_id: int, data: AccidentDetailIn
    ) -> LocationCondition:
        """Update an existing location condition"""
        obj = db.query(LocationCondition).filter(LocationCondition.claim_id == claim_id).first()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="LocationCondition not found"
            )

        for key, value in data.dict().items():
            setattr(obj, key, value)

        db.commit()
        db.refresh(obj)
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
        )
        db.add(db_passenger)
        db.commit()
        db.refresh(db_passenger)

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
    def update_passenger(id: int, payload, db: Session):
        print(id)
        print(payload)
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "PASSENGER",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Passenger not found or inactive")

        update_data = payload.dict(exclude_unset=True)

        # Handle nested address properly
        if "address" in update_data and update_data["address"] is not None:
            address_data = update_data.pop("address")
            if db_obj.address:  # update existing
                for key, value in address_data.items():
                    setattr(db_obj.address, key, value)
            else:  # create new
                new_address = Address(**address_data)
                db.add(new_address)
                db.flush()
                db_obj.address_id = new_address.id

        # Update remaining scalar fields
        for key, value in update_data.items():
            setattr(db_obj, key, value)

        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def deactivate_passenger(id: int, db: Session):
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "PASSENGER",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Passenger not found or already inactive")

        db_obj.is_active = False
        db.commit()
        return {"message": "Passenger deactivated successfully"}

    @staticmethod
    def create_witness(request, payload, db):
        tenant_id = get_tenant_id(request)

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
        )
        db.add(db_witness)
        db.commit()
        db.refresh(db_witness)
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
    def update_witness_detail(id: int, payload, db: Session):
        db_obj = db.query(ClientDetail).filter(
            ClientDetail.id == id,
            ClientDetail.role == "WITNESS",
            ClientDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Witness not found or inactive")

        update_data = payload.dict(exclude_unset=True)

        # ✅ Handle address separately
        if "address" in update_data and update_data["address"] is not None:
            address_data = update_data.pop("address")
            if db_obj.address:  # only update if exists
                for key, value in address_data.items():
                    setattr(db_obj.address, key, value)

        # ✅ Update other fields (not address)
        for key, value in update_data.items():
            setattr(db_obj, key, value)

        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def deactivate_witness_detail(id: int, db: Session):
        db_obj = db.query(ClientDetail).filter(ClientDetail.id == id).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Witness not found or already inactive")

        db_obj.is_active = False
        db.commit()
        return {"message": "witness deactivated successfully"}

    @staticmethod
    def create_police_detail(request: Request, payload: PoliceDetailIn, db: Session):
        tenant_id = get_tenant_id(request)

        db_police = PoliceDetail(
            claim_id=payload.claim_id,
            name=payload.name,
            reference_no=payload.reference_no,
            station_name=payload.station_name,
            station_address=payload.station_address,
            incident_report_taken=payload.incident_report_taken,
            report_received_date=payload.report_received_date,
            additional_info=payload.additional_info,
        )
        db.add(db_police)
        db.commit()
        db.refresh(db_police)
        return db_police

    @staticmethod
    def get_police_by_claim_id(claim_id: int, db: Session):
        return db.query(PoliceDetail).filter(
            PoliceDetail.claim_id == claim_id,
            PoliceDetail.is_active == True
        ).all()

    @staticmethod
    def update_police_detail(id: int, payload, db: Session):
        db_obj = db.query(PoliceDetail).filter(
            PoliceDetail.id == id,
            PoliceDetail.is_active == True
        ).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Police detail not found or inactive")

        for key, value in payload.dict(exclude_unset=True).items():
            setattr(db_obj, key, value)

        db.commit()
        db.refresh(db_obj)
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
    def deactivate_police_detail(id: int, db: Session):
        db_obj = db.query(PoliceDetail).filter(PoliceDetail.id == id).first()

        if not db_obj:
            raise HTTPException(status_code=404, detail="Police detail not found")

        db_obj.is_active = False
        db.commit()
        return {"message": "Police detail deactivated successfully"}