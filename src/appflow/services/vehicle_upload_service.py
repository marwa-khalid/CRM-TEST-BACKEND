# client_vehicle.py
from sqlalchemy.orm import Session
from libdata.models.tables import FuelType, VehicleDetail


def get_or_create_fuel_type(fuel_type: str, db: Session):
    # Check if the fuel type exists in the database
    existing_fuel_type = db.query(FuelType).filter(FuelType.label == fuel_type).first()

    if existing_fuel_type:
        # If it exists, return the fuel_type_id
        return existing_fuel_type.id
    else:
        # If it doesn't exist, create a new fuel type entry
        new_fuel_type = FuelType(label=fuel_type, is_active=True)
        new_fuel_type.sort_id = 1
        db.add(new_fuel_type)
        db.commit()
        db.refresh(new_fuel_type)
        return new_fuel_type.id


def update_vehicle_details(vehicle_details, extracted_data):
    # Update the vehicle details with the extracted data
    for field, value in extracted_data.items():
        if value:
            # Map "Number of seats" to "number_of_seat"
            if field == "Number of seats":
                vehicle_details["number_of_seat"] = value
            elif field != "fuel_type":  # Skip fuel_type as we handle it separately
                vehicle_details[field] = value


def process_client_vehicle(files, db: Session, ocr_service):
    vehicle_details = {
        "make": "",
        "model": "",
        "body_type": "",
        "registration": "",
        "color": "",
        "engine_size": "",
        "fuel_type_id": None,
        "transmission_id": None,
        "number_of_seat": "",
        "vehicle_category": ""
    }

    for file in files:
        extracted_data = ocr_service.process_file(file)

        # Update vehicle details with extracted data
        update_vehicle_details(vehicle_details, extracted_data)

        # Convert fuel_type → fuel_type_id
        if extracted_data.get("fuel_type"):
            fuel_type = extracted_data.get("fuel_type").strip().upper()
            fuel_type_id=get_or_create_fuel_type(fuel_type,db)
            vehicle_details["fuel_type_id"]=fuel_type_id

    return vehicle_details
