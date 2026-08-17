"""Fleet dashboard routers, split by module (Skyline hire vs Vehicle Management).

`router` combines both so the mount point in fleet/router.py stays a single include.
All endpoints keep their original /dashboard/* paths, so the frontend is unchanged."""
from fastapi import APIRouter

from fleet.routers.dashboard.skyline_router import router as skyline_router
from fleet.routers.dashboard.vm_router import router as vm_router

router = APIRouter()
router.include_router(skyline_router)
router.include_router(vm_router)
