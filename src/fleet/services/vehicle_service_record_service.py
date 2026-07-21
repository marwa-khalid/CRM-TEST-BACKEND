"""Servicing records for a vehicle — the Service Summary Log.

One record per uploaded Service Invoice; a vehicle accumulates them over its
lifetime with no cap (unlike licensing authorities, which are capped at four).
"""
from typing import List, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import S3Service
from fleet.models.tables import FleetVehicleService
from fleet.services.ocr import SERVICE_INTERVAL_MILES


def _base_query(db: Session, vehicle_record_id: int):
    return (
        db.query(FleetVehicleService)
        .filter(FleetVehicleService.vehicle_record_id == vehicle_record_id)
        .filter(FleetVehicleService.is_deleted.isnot(True))
    )


def list_services(db: Session, vehicle_record_id: int) -> List[FleetVehicleService]:
    """Oldest first, so "Service Invoice 1" is the earliest and the log reads
    chronologically."""
    return _base_query(db, vehicle_record_id).order_by(FleetVehicleService.id).all()


def create_service(
    db: Session, vehicle_record_id: int, actor: Optional[int] = None,
) -> FleetVehicleService:
    existing = list_services(db, vehicle_record_id)
    used = {s.position for s in existing if s.position}
    position = next(p for p in range(1, len(existing) + 2) if p not in used)
    record = FleetVehicleService(
        vehicle_record_id=vehicle_record_id, position=position,
        created_by=actor, updated_by=actor,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_service_or_404(db: Session, vehicle_record_id: int, service_id: int) -> FleetVehicleService:
    record = _base_query(db, vehicle_record_id).filter(FleetVehicleService.id == service_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Servicing record not found.")
    return record


def _apply_service_interval(record: FleetVehicleService, payload: dict) -> None:
    """Default Next Service Due At to serviced mileage + 10,000.

    Only fills it when the caller didn't set it explicitly and it is currently
    blank, so a manual amendment is never overwritten by a later mileage edit.
    """
    if "next_service_due_at" in payload:
        return
    mileage = payload.get("serviced_at_mileage", record.serviced_at_mileage)
    digits = "".join(ch for ch in str(mileage or "") if ch.isdigit())
    if digits and not (record.next_service_due_at or "").strip():
        payload["next_service_due_at"] = str(int(digits) + SERVICE_INTERVAL_MILES)


def update_service(
    db: Session, vehicle_record_id: int, service_id: int, payload: dict, actor: Optional[int] = None,
) -> FleetVehicleService:
    record = get_service_or_404(db, vehicle_record_id, service_id)
    _apply_service_interval(record, payload)
    for field, value in payload.items():
        if hasattr(record, field):
            setattr(record, field, value)
    record.updated_by = actor
    db.commit()
    db.refresh(record)
    return record


def delete_service(db: Session, vehicle_record_id: int, service_id: int) -> None:
    record = get_service_or_404(db, vehicle_record_id, service_id)
    record.is_deleted = True
    db.commit()


def upload_invoice(
    db: Session, vehicle_record_id: int, service_id: int, file: UploadFile,
) -> FleetVehicleService:
    record = get_service_or_404(db, vehicle_record_id, service_id)
    result = S3Service().upload_task_attachment_with_fallback(file)
    record.invoice_name = getattr(file, "filename", None)
    record.invoice_key = result.get("s3_key")
    record.invoice_url = result.get("file_url")
    db.commit()
    db.refresh(record)
    return record
