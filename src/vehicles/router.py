"""Vehicle Management module router aggregator.

The Vehicle Management module owns the standalone vehicle records (the vehicle
files) and the shared vehicle register (the pool that feeds the Claims & Skyline
hire dropdowns). Its public API lives under /vehicles.

The ORM models and business-logic services still live in the fleet package and
are imported one-way here — mirroring the frontend arrangement where src/vehicles
imports Fleet's shared kit but owns its own module surface.
"""
from fastapi import APIRouter, Depends

from fleet.deps import authenticate
from vehicles.routers.register_router import router as register_router
from vehicles.routers.vehicle_record_router import router as vehicle_record_router

# authenticate populates request.state (tenant_id/user_id) that child route deps
# read — the same global dependency the fleet router applies.
vehicles_router = APIRouter(prefix="/vehicles", tags=["Vehicles"], dependencies=[Depends(authenticate)])

vehicles_router.include_router(register_router)
vehicles_router.include_router(vehicle_record_router)
