"""Fleet module router aggregator.

The public API stays under /fleet, while each screen/domain owns its own router.
"""
from fastapi import APIRouter, Depends

from fleet.deps import authenticate
from fleet.routers.document_router import router as document_router
from fleet.routers.email_router import router as email_router
from fleet.routers.generated_document_router import router as generated_document_router
from fleet.routers.hire_router import router as hire_router
from fleet.routers.ocr_router import router as ocr_router
from fleet.routers.payment_router import router as payment_router
from fleet.routers.pcn_router import router as pcn_router
from fleet.routers.sms_router import router as sms_router
from fleet.routers.vehicle_router import router as vehicle_router

# authenticate populates request.state (tenant_id/user_id) that child route deps read.
fleet_router = APIRouter(prefix="/fleet", tags=["Fleet"], dependencies=[Depends(authenticate)])

fleet_router.include_router(ocr_router)
fleet_router.include_router(hire_router)
fleet_router.include_router(vehicle_router)
fleet_router.include_router(document_router)
fleet_router.include_router(generated_document_router)
fleet_router.include_router(payment_router)
fleet_router.include_router(email_router)
fleet_router.include_router(pcn_router)
fleet_router.include_router(sms_router)
