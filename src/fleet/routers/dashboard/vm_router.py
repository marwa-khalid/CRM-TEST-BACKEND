"""Vehicle-Management (CAMS / Skyline VM) dashboard endpoints: status donut, vehicle
list, Servicing Due, Compliance and Expiry cards. All scoped by ``context`` (cams |
skyline); the logic lives in the dashboard `vm` service."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fleet.deps import get_session, get_tenant_id
from fleet.services.dashboard import vm as vm_svc

router = APIRouter()


@router.get("/dashboard/servicing-due")
def servicing_due_route(
    context: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Servicing Due card — Overdue / Weekly / Monthly buckets with vehicle mileage.
    ``context`` (cams | skyline) scopes to one Vehicle Management side."""
    return vm_svc.get_servicing_due(db, tenant_id, context=context or None)


@router.get("/dashboard/vehicle-status")
def vehicle_status_route(
    context: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Vehicle-status distribution for the donut. ``context`` (cams | skyline) scopes
    to one Vehicle Management side."""
    return vm_svc.get_vehicle_status(db, tenant_id, context=context or None)


@router.get("/dashboard/vehicles")
def fleet_vehicles_route(
    context: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Live vehicle list for the "Skyline Vehicles" section (status + hire info).
    ``context`` (cams | skyline) scopes to one Vehicle Management side."""
    return vm_svc.get_fleet_vehicles(db, tenant_id, context=context or None)


@router.get("/dashboard/compliance")
def compliance_route(
    context: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Per-category compliance summary (MOT / Plate / Road Fund / Service).
    ``context`` (cams | skyline) scopes to one Vehicle Management side."""
    return vm_svc.get_compliance(db, tenant_id, context=context or None)


@router.get("/dashboard/expiries")
def expiries_route(
    context: str = "",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant_id),
):
    """Expiry cards (Road Fund / MOT / Plate): tab counts + soonest rows.
    ``context`` (cams | skyline) scopes to one Vehicle Management side."""
    return vm_svc.get_expiries(db, tenant_id, context=context or None)
