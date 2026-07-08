from __future__ import annotations

import traceback
from typing import Iterable, List

from fastapi import UploadFile

from appflow.services.import_job_service import FilePayload, import_job_service
from appflow.services.import_utils import build_upload_files
from appflow.services.ocr_Service import ocr_service
from appflow.services.ocr_engineer_service import engineer_ocr_service, process_engineer_detail
from appflow.services.ocr_owner_service import owner_ocr_service
from appflow.services.vehicle_owner_upload_service import process_vehicle_owner,vehicle_ocr_service
from appflow.services.vehicle_upload_service import process_client_vehicle,vehicle_detail_ocr_service
from libdata.settings import get_session_ctx


def _cleanup_uploads(uploads: Iterable[UploadFile]) -> None:
    for upload in uploads:
        try:
            upload.file.close()
        except Exception:
            continue


def _notify_import_done(actor_id: int, tenant_id: int, kind: str, ok: bool = True) -> None:
    """System alert when a background import finishes (own session; never raises)."""
    if not actor_id:
        return
    try:
        from appflow.services.notification_service import create_notification
        with get_session_ctx() as db:
            create_notification(
                db, recipient_user_id=actor_id, tenant_id=tenant_id, actor_user_id=actor_id,
                category="System Alert", tab="System",
                title="Import Completed" if ok else "Import Failed",
                description=(f"Your {kind} import finished processing."
                            if ok else f"Your {kind} import failed. Please try again."),
            )
    except Exception:
        pass


def run_client_vehicle_import(job_id: str, payloads: List[FilePayload], claim_id: int, actor_id: int,tenant_id: int) -> None:
    import_job_service.mark_processing(job_id)
    uploads = build_upload_files(payloads)
    try:
        with get_session_ctx() as db:
            result = process_client_vehicle(uploads, db, vehicle_detail_ocr_service, claim_id, actor_id,tenant_id)
        import_job_service.mark_completed(job_id, result)
        _notify_import_done(actor_id, tenant_id, "vehicle details")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        traceback.print_exc()  # surface the real error in the Railway logs
        import_job_service.mark_failed(job_id, str(exc))
        _notify_import_done(actor_id, tenant_id, "vehicle details", ok=False)
    finally:
        _cleanup_uploads(uploads)


def run_vehicle_owner_import(job_id: str, payloads: List[FilePayload], claim_id: int, actor_id: int,tenant_id: int) -> None:
    import_job_service.mark_processing(job_id)
    uploads = build_upload_files(payloads)
    try:
        with get_session_ctx() as db:
            owners, uploaded_files = process_vehicle_owner(uploads, db, vehicle_ocr_service, claim_id, actor_id,tenant_id)
        import_job_service.mark_completed(
            job_id,
            {
                "vehicle_owner_detail": owners,
                "uploaded_files": uploaded_files,
            },
        )
        _notify_import_done(actor_id, tenant_id, "vehicle owner")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        traceback.print_exc()  # surface the real error in the Railway logs
        import_job_service.mark_failed(job_id, str(exc))
        _notify_import_done(actor_id, tenant_id, "vehicle owner", ok=False)
    finally:
        _cleanup_uploads(uploads)


def run_engineer_detail_import(job_id: str, payloads: List[FilePayload], claim_id: int, actor_id: int,tenant_id: int) -> None:
    import_job_service.mark_processing(job_id)
    uploads = build_upload_files(payloads)
    try:
        with get_session_ctx() as db:
            engineer_details, uploaded_files = process_engineer_detail(uploads, db, engineer_ocr_service, claim_id, actor_id,tenant_id)
        import_job_service.mark_completed(
            job_id,
            {
                "engineer_detail": engineer_details,
                "uploaded_files": uploaded_files,
            },
        )
        _notify_import_done(actor_id, tenant_id, "engineer report")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        traceback.print_exc()  # surface the real error in the Railway logs
        import_job_service.mark_failed(job_id, str(exc))
        _notify_import_done(actor_id, tenant_id, "engineer report", ok=False)
    finally:
        _cleanup_uploads(uploads)

