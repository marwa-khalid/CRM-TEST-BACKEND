from fastapi import APIRouter, Depends
from appflow.router.claims import claims_router
from appflow.router.lookups_public import lookup_router
from libauth.auth import authenticate
from appflow.router.referrers import referrers_router
from appflow.router.client_detail import client_router
from appflow.router.accident_detail import accident_router
from appflow.router.vehicle_detail import vehicle_router
from appflow.router.witness_email import email_router

root_router = APIRouter(dependencies=[Depends(authenticate)])

@root_router.get("/")
def root():
    return {"message": "API is running"}


root_router.include_router(lookup_router)

root_router.include_router(claims_router)

root_router.include_router(referrers_router)

root_router.include_router(client_router)

root_router.include_router(accident_router)

root_router.include_router(vehicle_router)

root_router.include_router(email_router)