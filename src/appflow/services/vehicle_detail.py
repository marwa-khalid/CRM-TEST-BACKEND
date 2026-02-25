from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from libdata.models.tables import VehicleDetail, Borough, ThirdPartyVehicle, Claim
from appflow.models.vehicle_detail import (
    ClientVehicleCreate, ClientVehicleResponse,
    BoroughCreate,
    ThirdPartyVehicleCreate
)

def normalize_claim_type(claim_type: str) -> str:
    # Normalize any non-standard dash characters to standard hyphen
    return claim_type.replace("–", "-")

def create_client_vehicle(vehicle_data: ClientVehicleCreate, db: Session) -> VehicleDetail:
    # Validate claim
    claim = db.query(Claim).filter(Claim.id == vehicle_data.claim_id).first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    claim_type_label = normalize_claim_type(claim.claim_type.label.strip())  # Normalize and remove extra spaces

    # Check for RTA-NA or RTA CAMS claim types and ensure borough is provided
    if claim_type_label in ["RTA-NA"]:
        if not vehicle_data.borough:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Borough information is required"
            )

    # Create Client Vehicle
    vehicle = VehicleDetail(
        claim_id=vehicle_data.claim_id,
        make=vehicle_data.make,
        model=vehicle_data.model,
        body_type=vehicle_data.body_type,
        registration=vehicle_data.registration,
        color=vehicle_data.color,
        fuel_type_id=vehicle_data.fuel_type_id,
        engine_size=vehicle_data.engine_size,
        transmission_id=vehicle_data.transmission_id,
        number_of_seat=vehicle_data.number_of_seat,
        vehicle_category=vehicle_data.vehicle_category,
        tenant_id=claim.tenant_id,
    )
    db.add(vehicle)
    db.flush()  # to get vehicle.id

    # Borough
    if vehicle_data.borough:
        borough = Borough(
            client_vehicle_id=vehicle.id,
            borough_name=vehicle_data.borough.borough_name,
            taxi_type_id=vehicle_data.borough.taxi_type_id,
            client_badge_number=vehicle_data.borough.client_badge_number,
            badge_expiration_date=vehicle_data.borough.badge_expiration_date,
            vehicle_badge_number=vehicle_data.borough.vehicle_badge_number,
            any_other_borough=vehicle_data.borough.any_other_borough,
            other_borough_name=vehicle_data.borough.other_borough_name,
            tenant_id=claim.tenant_id,
        )
        db.add(borough)

    # Third Party Vehicles
    for i, tp_data in enumerate(vehicle_data.third_party_vehicles, start=1):
        tp_vehicle = ThirdPartyVehicle(
            client_vehicle_id=vehicle.id,
            sequence=i,
            make=tp_data.make,
            model=tp_data.model,
            registration=tp_data.registration,
            color=tp_data.color,
            images_available=tp_data.images_available,
        )
        db.add(tp_vehicle)

    db.commit()
    db.refresh(vehicle)
    return vehicle

def update_client_vehicle(claim_id: int, vehicle_data: ClientVehicleCreate, db: Session) -> VehicleDetail:
    # Get the existing vehicle based on claim_id
    vehicle = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client vehicle not found")

    # Get the claim to validate claim type
    claim = db.query(Claim).filter(Claim.id == vehicle.claim_id).first()
    claim_type_label = normalize_claim_type(claim.claim_type.label.strip())  # Normalize claim type label

    # Ensure borough information is provided for RTA-NA or RTA CAMS claim types
    if claim_type_label in ["RTA-NA", "RTA CAMS"]:
        if not vehicle_data.borough:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Borough information is Required"
            )

    # Update the base fields of the vehicle
    for field, value in vehicle_data.dict(exclude={"borough", "third_party_vehicles"}).items():
        setattr(vehicle, field, value)

    # Update or add Borough information
    if vehicle_data.borough:
        if vehicle.borough:
            # If borough exists, update it
            for field, value in vehicle_data.borough.dict().items():
                setattr(vehicle.borough, field, value)
        else:
            # If no borough exists, create a new one
            borough = Borough(client_vehicle_id=vehicle.id, **vehicle_data.borough.dict())
            db.add(borough)

    # Update Third Party Vehicles (replace all old entries)
    db.query(ThirdPartyVehicle).filter(ThirdPartyVehicle.client_vehicle_id == vehicle.id).delete()
    for i, tp_data in enumerate(vehicle_data.third_party_vehicles, start=1):
        tp_vehicle = ThirdPartyVehicle(
            client_vehicle_id=vehicle.id,
            sequence=i,
            **tp_data.dict()
        )
        db.add(tp_vehicle)

    db.commit()
    db.refresh(vehicle)
    return vehicle

def get_client_vehicle(claim_id: int, db: Session) -> VehicleDetail:
    vehicle = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client vehicle not found")
    return vehicle


def list_client_vehicles(claim_id: int, db: Session):
    return db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).all()


def delete_client_vehicle(vehicle_id: int, db: Session):
    vehicle = get_client_vehicle(vehicle_id, db)
    db.delete(vehicle)
    db.commit()
    return {"message": "Client vehicle deleted successfully"}