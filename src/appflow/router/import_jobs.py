from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from appflow.services.import_job_service import ImportJobStatus, import_job_service

import_job_router = APIRouter(prefix="/import-jobs", tags=["Import Jobs"])


@import_job_router.get("/{job_id}/status")
def get_import_job_status(job_id: str):
    job = import_job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = job.to_dict()
    if job.status == ImportJobStatus.FAILED:
        payload["error"] = job.error
    return payload


@import_job_router.get("/{job_id}/result")
def get_import_job_result(job_id: str):
    job = import_job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == ImportJobStatus.COMPLETED:
        return {
            "job_id": job.id,
            "status": job.status.value,
            "result": job.result,
        }

    if job.status == ImportJobStatus.FAILED:
        raise HTTPException(status_code=500, detail={"job_id": job.id, "error": job.error})

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.id,
            "status": job.status.value,
        },
    )


