from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Request
from sqlalchemy.orm import Session

from libdata.settings import get_session
from appflow.models.task import TaskCreate, TaskUpdate, TaskOut, TaskListOut, TaskStatsOut, ReassignRequest, NoteCreate
from appflow.services.task_service import TaskService
from appflow.services import task_note_service
from appflow.services.s3_service import S3Service
from appflow.utils import actor_id, get_tenant_id

task_router = APIRouter(prefix="/tasks", tags=["Tasks"])


@task_router.get("/", response_model=TaskListOut)
def list_tasks(
    search: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    department: Optional[str] = None,
    assigned_user: Optional[str] = None,
    claim_reference: Optional[str] = None,
    vehicle_registration: Optional[str] = None,
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 10,
    all_users: bool = False,
    exclude_overdue: bool = False,
    db: Session = Depends(get_session),
    tenant_id=Depends(get_tenant_id),
    current_user=Depends(actor_id),
):
    # all_users=True returns every task in the tenant (used by the Dashboard task
    # cards, which are a system-wide overview); otherwise tasks are scoped to the
    # logged-in user (the Task Management list).
    return TaskService.list_tasks(
        db, tenant_id, search, status, priority, department, assigned_user,
        claim_reference, vehicle_registration, due_from, due_to, page, page_size,
        exclude_overdue=exclude_overdue,
        current_user_id=None if all_users else current_user,
    )


@task_router.get("/stats", response_model=TaskStatsOut)
def task_stats(
    db: Session = Depends(get_session),
    tenant_id=Depends(get_tenant_id),
    current_user=Depends(actor_id),
):
    return TaskService.get_stats(db, tenant_id, current_user_id=current_user)


@task_router.get("/vehicle-options")
def vehicle_options(db: Session = Depends(get_session), tenant_id=Depends(get_tenant_id)):
    """Distinct vehicle registrations for the Vehicle Reg. dropdown (tenant-wide)."""
    return TaskService.vehicle_options(db, tenant_id)


@task_router.post("/upload")
async def upload_task_attachment(file: UploadFile = File(...)):
    """Upload a task attachment and return the stored path."""
    result = S3Service().upload_task_attachment_with_fallback(file)
    return {"path": result["s3_key"], "filename": Path(file.filename or "file").name}


@task_router.get("/attachment-url")
def task_attachment_url(key: str, request: Request):
    """Return a short-lived presigned URL to view/download a task attachment."""
    if key.startswith("/uploads/") or key.startswith("uploads/"):
        return {"url": f"{str(request.base_url).rstrip('/')}/{key.lstrip('/')}"}
    return {"url": S3Service().generate_presigned_download_url(s3_key=key, expires_in_seconds=3600)}


@task_router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_session)):
    return TaskService.get_task(task_id, db)


@task_router.post("/", response_model=TaskOut)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
    tenant_id=Depends(get_tenant_id),
):
    return TaskService.create_task(payload, db, current_user, tenant_id)


@task_router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
):
    return TaskService.update_task(task_id, payload, db, current_user)


@task_router.post("/{task_id}/reassign", response_model=TaskOut)
def reassign_task(
    task_id: int,
    payload: ReassignRequest,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
):
    return TaskService.reassign_task(task_id, payload, db, current_user)


@task_router.delete("/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
):
    return TaskService.delete_task(task_id, db, current_user)


# ── notes ──────────────────────────────────────────────────────────────────
@task_router.get("/{task_id}/notes")
def list_task_notes(task_id: int, db: Session = Depends(get_session)):
    return task_note_service.list_notes(db, task_id)


@task_router.post("/{task_id}/notes")
def add_task_note(
    task_id: int,
    payload: NoteCreate,
    db: Session = Depends(get_session),
    current_user=Depends(actor_id),
    tenant_id=Depends(get_tenant_id),
):
    return task_note_service.add_note(db, task_id, payload.text, current_user, tenant_id)


@task_router.delete("/notes/{note_id}")
def delete_task_note(note_id: int, db: Session = Depends(get_session), current_user=Depends(actor_id)):
    return task_note_service.delete_note(db, note_id, current_user)


# ── history ────────────────────────────────────────────────────────────────
@task_router.get("/{task_id}/history")
def task_history(task_id: int, db: Session = Depends(get_session)):
    return task_note_service.list_history(db, task_id)
