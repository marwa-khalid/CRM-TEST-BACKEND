from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class ImportJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FilePayload:
    filename: str
    content_type: Optional[str]
    data: bytes


@dataclass
class ImportJob:
    id: str
    job_type: str
    status: ImportJobStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.id,
            "job_type": self.job_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error": self.error,
        }


class ImportJobService:
    def __init__(self):
        self._jobs: Dict[str, ImportJob] = {}
        self._lock = threading.Lock()

    def create_job(self, job_type: str) -> ImportJob:
        job_id = str(uuid.uuid4())
        job = ImportJob(id=job_id, job_type=job_type, status=ImportJobStatus.PENDING)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def mark_processing(self, job_id: str) -> None:
        self._update_job(job_id, status=ImportJobStatus.PROCESSING)

    def mark_completed(self, job_id: str, result: Any) -> None:
        self._update_job(job_id, status=ImportJobStatus.COMPLETED, result=result, error=None)

    def mark_failed(self, job_id: str, error: str) -> None:
        self._update_job(job_id, status=ImportJobStatus.FAILED, error=error)

    def get_job(self, job_id: str) -> Optional[ImportJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def _update_job(
        self,
        job_id: str,
        *,
        status: Optional[ImportJobStatus] = None,
        result: Any = None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            if status:
                job.status = status
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error

            job.updated_at = datetime.now(timezone.utc)
            self._jobs[job_id] = job


import_job_service = ImportJobService()

