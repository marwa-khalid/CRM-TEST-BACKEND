from fastapi import APIRouter, Depends, UploadFile, File, Request,Query
from sqlalchemy.orm import Session
from appflow.utils import actor_id, get_tenant_id
from libdata.settings import get_session
from appflow.models.history_logs import HistoryActivityOut
from appflow.services.history_activity_service import HistoryActivityService
from libdata.models.tables import HistoryActivities,User
from typing import List,Optional
from fastapi.responses import FileResponse
from fastapi import Request, HTTPException
from datetime import timedelta, datetime

history_router = APIRouter(prefix="/history", tags=["History Activities"])

@history_router.post("/upload", response_model=List[HistoryActivityOut])
async def upload_history_files(
    claim_id: int,
    request: Request,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
    tenant_id: int = Depends(get_tenant_id)
):
    uploaded_histories = []

    for file in files:
        history, created_by_name = HistoryActivityService.upload_file(
            claim_id=claim_id,
            file=file,
            actor_id=current_user,
            tenant_id=tenant_id,
            db=db,
        )
        uploaded_histories.append(
            HistoryActivityOut.from_orm_with_url((history, created_by_name), request)
        )

    return uploaded_histories


@history_router.get("/files", response_model=List[HistoryActivityOut])
async def list_history_files(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    records = HistoryActivityService.list_files(claim_id, db)

    return [
        HistoryActivityOut.from_orm_with_url(rec, request)
        for rec in records
    ]

@history_router.get("/download/{history_id}")
async def download_history_file(
    history_id: int,
    db: Session = Depends(get_session)
):
    file_path, download_name = HistoryActivityService.get_file_path(history_id, db)

    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/octet-stream"
    )

@history_router.put("/deactivate/{history_id}")
async def deactivate_history(
    history_id: int,
    db: Session = Depends(get_session),
    current_user: int = Depends(actor_id),
):
    """
    Deactivate a history file (is_active=False, is_deleted=True) and update updated_by
    """
    record = HistoryActivityService.deactivate_history(history_id, current_user, db)
    return {"detail": f"History record {history_id} deactivated successfully"}

@history_router.get("/tenant-files", response_model=List[HistoryActivityOut])
async def list_tenant_history_files(
    tenant_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    """
    Fetch all history files for a tenant, sorted by created_at descending
    """
    records = HistoryActivityService.list_by_tenant(tenant_id, db)

    return [
        HistoryActivityOut.from_orm_with_url(rec, request)
        for rec in records
    ]

@history_router.get("/claim/{claim_id}/files", response_model=List[HistoryActivityOut])
async def get_claim_files_by_type(
        claim_id: int,
        request: Request,
        db: Session = Depends(get_session),
):
    """
    Get all files for a claim with types ENGINEER_DETAIL and HISTORYUPLOAD
    Includes file URLs for download
    """
    records = HistoryActivityService.get_files_by_type(claim_id, db)

    return [
        HistoryActivityOut.from_orm_with_url(rec, request)
        for rec in records
    ]


@history_router.get("/paginated-tenant-files", response_model=dict)
async def list_tenant_history_files(
    tenant_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_session),
):
    """
    Paginated history files for a tenant
    """
    data, total = HistoryActivityService.list_by_tenant_paginated(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        db=db
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            HistoryActivityOut.from_orm_with_url(row, request)
            for row in data
        ]
    }

@history_router.get("/paginated-files", response_model=dict)
async def list_history_files(
    claim_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_session),
):
    """
    Paginated history files for a claim
    """
    records, total = HistoryActivityService.list_files_paginated(claim_id, page, page_size, db)

    items = [HistoryActivityOut.from_orm_with_url(row, request) for row in records]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }

@history_router.get("/search-tenant-files", response_model=dict)
async def search_tenant_history_files(
    tenant_id: int,
    search: Optional[str] = Query(
        None,
        description="Search in file title and user name"
    ),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    request: Request = None,
    db: Session = Depends(get_session),
):
    data, total = HistoryActivityService.search_by_tenant(
        tenant_id=tenant_id,
        search=search,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        db=db
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            HistoryActivityOut.from_orm_with_url(row, request)
            for row in data
        ]
    }

@history_router.get("/search-claim-files", response_model=dict)
async def search_claim_files(
    claim_id: int = Query(..., description="Claim ID to search files"),
    search: Optional[str] = Query(None, description="Search in file title and creator name"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_session),
    request: Request = None,
):
    """
    Search history files for a specific claim with optional filters.
    Supports:
      - search: file name OR creator name
      - start_date / end_date: filter by creation date
      - pagination
    """
    records, total = HistoryActivityService.search_files_by_claim_advanced(
        claim_id=claim_id,
        search=search,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        db=db
    )

    items = [HistoryActivityOut.from_orm_with_url(row, request) for row in records]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }