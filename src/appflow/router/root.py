from fastapi import APIRouter, Depends
from appflow.router.claims import claims_router
from appflow.router.lookups_public import lookup_router
from libauth.auth import authenticate
from appflow.router.referrers import referrers_router
from appflow.router.client_detail import client_router
from appflow.router.accident_detail import accident_router
from appflow.router.vehicle_detail import vehicle_router
from appflow.router.witness_email import email_router
from appflow.router.vehicle_owner import vehicle_owner_router
from appflow.router.engineer_detail import engineer_router
from appflow.router.route_repair import router
from appflow.router.total_loss import loss_router
from appflow.router.insurer_broker import insurer_router
from appflow.router.panel_solicitor import panel_solicitor_router
from appflow.router.storage_recovery import storage_recovery_router
from appflow.router.third_party_insurer import third_party_insurer_router
from appflow.router.roboflow import roboflow_router
from appflow.router.hire_detail import hire_detail_router
from appflow.router.driver_document_agreement import driver_documents_router
from appflow.router.hire_vehicle_provided import hire_vehicle_provided_router
from appflow.router.driver_check import driver_check_router
from appflow.router.history_activity import history_router
from appflow.router.import_jobs import import_job_router
from appflow.router.case_activity import case_activity_router
from appflow.router.document_library import document_library_router
from appflow.router.vehicle_damage_ai_report import vehicle_damage_report_router
from appflow.router.hire_record import hire_record_router
from appflow.router.plating_charges import plating_charges_router
from appflow.router.abi_bhr_charges import abi_bhr_charges_router
from appflow.router.comparison_settlement import comparison_settlement_router
from appflow.router.hire_payment_details import hire_payment_details_router
from appflow.router.direct_hire_payment import direct_hire_payment_router
from appflow.router.account_settings import account_settings_router
from appflow.router.task import task_router
from appflow.router.users import users_router
from appflow.router.notification import notification_router
from appflow.router.dashboard import dashboard_router
from appflow.router.calendar_event import calendar_event_router

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

root_router.include_router(vehicle_owner_router)

root_router.include_router(engineer_router)

root_router.include_router(router)

root_router.include_router(loss_router)

root_router.include_router(insurer_router)

root_router.include_router(panel_solicitor_router)

root_router.include_router(storage_recovery_router)

root_router.include_router(third_party_insurer_router)

root_router.include_router(roboflow_router)

root_router.include_router(hire_detail_router)

root_router.include_router(driver_documents_router)

root_router.include_router(hire_vehicle_provided_router)

root_router.include_router(driver_check_router)

root_router.include_router(history_router)

root_router.include_router(case_activity_router)

root_router.include_router(document_library_router)

root_router.include_router(vehicle_damage_report_router)

root_router.include_router(hire_record_router)
root_router.include_router(plating_charges_router)
root_router.include_router(abi_bhr_charges_router)
root_router.include_router(comparison_settlement_router)
root_router.include_router(hire_payment_details_router)
root_router.include_router(direct_hire_payment_router)
root_router.include_router(account_settings_router)
root_router.include_router(task_router)
root_router.include_router(users_router)
root_router.include_router(notification_router)
root_router.include_router(dashboard_router)
root_router.include_router(calendar_event_router)
