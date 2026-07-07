import os
from datetime import datetime
from fastapi import HTTPException, UploadFile,Request
from sqlalchemy.orm import Session
from libdata.enums import HistoryLogType
from libdata.models.tables import HistoryActivities, Claim,User
import urllib.parse
from appflow.utils import build_case_reference
from sqlalchemy import func
from datetime import timedelta
from typing import Optional, Tuple
from sqlalchemy import and_, or_
from sqlalchemy import cast, Date

UPLOAD_DIR = "uploads/history"

class HistoryActivityService:

    @staticmethod
    def upload_file(
        claim_id: int,
        file: UploadFile,
        actor_id: int,
        tenant_id:int,
        db: Session,
    ):
        # Validate claim exists
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail=f"Claim with id {claim_id} does not exist")

        # Validate extension
        if not file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
            raise HTTPException(status_code=400, detail="File must be PNG/JPG/PDF")

        # timestamp dir
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        target_dir = os.path.join(UPLOAD_DIR, str(claim_id), ts)
        os.makedirs(target_dir, exist_ok=True)

        # cleanup filename
        safe_name = file.filename.replace("/", "_").replace("..", "_")
        full_path = os.path.join(target_dir, safe_name)

        # Write file
        with open(full_path, "wb") as buffer:
            buffer.write(file.file.read())

        # store normalized path (for APIs / frontend usage)
        rel_path = "/" + os.path.relpath(full_path, UPLOAD_DIR).replace("\\", "/")

        reference = build_case_reference(claim_id,db)
        history = HistoryActivities(
            claim_id=claim_id,
            file_name=f"The file named {safe_name} has been saved for claim {reference}",
            file_path=rel_path,
            file_type=HistoryLogType.HISTORYUPLOAD,
            created_by=actor_id,
            updated_by=actor_id,
            tenant_id=tenant_id,
        )

        db.add(history)
        db.commit()
        db.refresh(history)
        actor_name = db.query(
            func.concat(User.first_name, ' ', User.last_name)
        ).filter(User.id == actor_id).scalar()
        return history,actor_name

    @staticmethod
    def list_files(claim_id: int, db: Session):
        return (
            db.query(
                HistoryActivities,
                func.concat(User.first_name, " ", User.last_name).label("created_by_name")
            )
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.claim_id == claim_id,
                HistoryActivities.is_active == True,
                HistoryActivities.is_deleted == False
            )
            .order_by(HistoryActivities.created_at.desc())
            .all()
        )

    @staticmethod
    def get_file_path(history_id: int, db: Session) -> tuple[str, str]:
        record = db.query(HistoryActivities).filter(HistoryActivities.id == history_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="File not found in history")

        # Decode URL-encoded path
        decoded_path = urllib.parse.unquote(record.file_path.lstrip("/"))

        # Normalize slashes for the OS
        normalized_path = os.path.normpath(decoded_path)

        # Absolute path on the server
        file_path = os.path.join(UPLOAD_DIR, normalized_path)

        # Check if file exists
        if not os.path.isfile(file_path):
            # Try with original encoded filename as fallback
            file_path_encoded = os.path.join(UPLOAD_DIR, record.file_path.lstrip("/").replace("/", os.sep))
            if os.path.isfile(file_path_encoded):
                file_path = file_path_encoded
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"File not found on server: {file_path}"
                )

        claim_number = str(record.claim_id).zfill(5)
        original_name = os.path.basename(file_path)
        download_name = f"ClaimFile-{claim_number}-{original_name}"

        return file_path, download_name

    @staticmethod
    def deactivate_history(history_id: int, actor_id: int, db: Session):
        """
        Deactivate a history record: set is_active=False, is_deleted=True, updated_by=actor_id
        """
        record = db.query(HistoryActivities).filter(HistoryActivities.id == history_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="History record not found")

        record.is_active = False
        record.is_deleted = True
        record.updated_by = actor_id

        db.add(record)
        db.commit()
        db.refresh(record)

        return record

    @staticmethod
    def create_activity(
            db,
            claim_id: int,
            file_name: str,
            file_path: str,
            file_type: HistoryLogType,
            user_id: int,
            tenant_id: int = None
    ):
        # Validate claim exists
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise ValueError(f"Claim with id {claim_id} does not exist")

        activity = HistoryActivities(
            claim_id=claim_id,
            file_name=file_name,
            file_path=file_path,
            file_type=file_type,
            created_by=user_id,
            updated_by=user_id,
            tenant_id=tenant_id
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
        return activity

    @staticmethod
    def list_by_tenant(tenant_id: int, db: Session):
        """
        Fetch all history activities for a tenant, sorted by created_at descending
        """
        return (
            db.query(HistoryActivities,
                func.concat(User.first_name, " ", User.last_name).label("created_by_name"))
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.tenant_id == tenant_id,
                HistoryActivities.is_active == True,
                HistoryActivities.is_deleted == False,
            )
            .order_by(HistoryActivities.created_at.desc())
            .all()
        )

    # In your HistoryActivityService class, add this method:

    @staticmethod
    def get_files_by_type(claim_id: int, db: Session):
        """
        Get files for a claim with specific types: ENGINEER_DETAIL and HISTORYUPLOAD
        """
        return (
            db.query(
                HistoryActivities,
                func.concat(User.first_name, " ", User.last_name).label("created_by_name")
            )
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.claim_id == claim_id,
                HistoryActivities.file_type.in_([
                    HistoryLogType.ENGINEER_DETAIL,
                    HistoryLogType.HISTORYUPLOAD
                ]),
                HistoryActivities.is_active == True,
                HistoryActivities.is_deleted == False
            )
            .order_by(HistoryActivities.created_at.desc())
            .all()
        )

    @staticmethod
    def list_by_tenant_paginated(
            tenant_id: int,
            page: int,
            page_size: int,
            db: Session
    ) -> tuple[list, int]:
        """
        Fetch paginated history activities for a tenant
        """

        base_query = (
            db.query(
                HistoryActivities,
                func.concat(User.first_name, " ", User.last_name).label("created_by_name")
            )
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.tenant_id == tenant_id,
                HistoryActivities.is_active == True,
                HistoryActivities.is_deleted == False,
            )
        )

        total = base_query.count()

        items = (
            base_query
            .order_by(HistoryActivities.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return items, total

    @staticmethod
    def list_files_paginated(claim_id: int, page: int, page_size: int, db: Session) -> tuple[list, int]:
        """
        Fetch paginated history activities for a claim
        Returns a tuple: (list of rows, total count)
        """
        base_query = (
            db.query(
                HistoryActivities,
                func.concat(User.first_name, " ", User.last_name).label("created_by_name")
            )
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.claim_id == claim_id,
                HistoryActivities.is_active == True,
                HistoryActivities.is_deleted == False
            )
        )

        # Get total number of records
        total = base_query.count()

        # Apply pagination
        items = (
            base_query
            .order_by(HistoryActivities.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return items, total

    @staticmethod
    def search_by_tenant(
            tenant_id: int,
            search: Optional[str],
            start_date: Optional[str],
            end_date: Optional[str],
            page: int = 1,
            page_size: int = 20,
            db: Session = None
    ) -> Tuple[list, int]:
        """
        Search tenant history by:
        - search → file_name OR user full name
        - start_date & end_date → DATE based filtering (timezone safe)
        """

        query = (
            db.query(
                HistoryActivities,
                func.concat(User.first_name, " ", User.last_name).label("created_by_name")
            )
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.tenant_id == tenant_id,
                HistoryActivities.is_active.is_(True),
                HistoryActivities.is_deleted.is_(False),
            )
        )

        # 🔍 Combined search (file title OR user name)
        if search:
            like_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    HistoryActivities.file_name.ilike(like_pattern),
                    func.concat(User.first_name, " ", User.last_name).ilike(like_pattern)
                )
            )

        # 📅 DATE-based filtering (FIXES TIMEZONE ISSUE)
        if start_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                query = query.filter(
                    cast(HistoryActivities.created_at, Date) >= start
                )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid start_date format. Use YYYY-MM-DD"
                )

        if end_date:
            try:
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
                query = query.filter(
                    cast(HistoryActivities.created_at, Date) <= end
                )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid end_date format. Use YYYY-MM-DD"
                )

        total = query.count()

        items = (
            query
            .order_by(HistoryActivities.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return items, total


    @staticmethod
    def search_files_by_claim_advanced(
            claim_id: int,
            search: Optional[str],
            start_date: Optional[str],
            end_date: Optional[str],
            page: int = 1,
            page_size: int = 20,
            db: Session = None
    ):
        """
        Search history files for a specific claim with:
          - search: file name OR creator full name
          - start_date / end_date: filter by creation date
          - pagination
        """
        query = (
            db.query(
                HistoryActivities,
                func.concat(User.first_name, " ", User.last_name).label("created_by_name")
            )
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.claim_id == claim_id,
                HistoryActivities.is_active.is_(True),
                HistoryActivities.is_deleted.is_(False)
            )
        )

        # 🔍 Combined search (file name OR user full name)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    HistoryActivities.file_name.ilike(pattern),
                    func.concat(User.first_name, " ", User.last_name).ilike(pattern)
                )
            )

        # 📅 Date filtering
        if start_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                query = query.filter(cast(HistoryActivities.created_at, Date) >= start)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")

        if end_date:
            try:
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
                query = query.filter(cast(HistoryActivities.created_at, Date) <= end)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")

        total = query.count()

        records = (
            query
            .order_by(HistoryActivities.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return records, total