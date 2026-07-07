from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict


class CaseDocumentAuditLogOut(BaseModel):
    id: int
    action: str
    action_detail: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CaseDocumentVersionOut(BaseModel):
    id: int
    version: int
    file_name: str
    file_url: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    is_latest: bool

    model_config = ConfigDict(from_attributes=True)


class CaseDocumentListItemOut(BaseModel):
    id: int
    claim_id: int
    file_name: str
    original_filename: Optional[str] = None
    file_extension: Optional[str] = None
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    category: str
    tag: Optional[str] = None
    source_type: Optional[str] = None
    file_url: Optional[str] = None
    version: int
    is_latest: bool
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CaseDocumentDetailOut(BaseModel):
    id: int
    claim_id: int
    file_name: str
    original_filename: Optional[str] = None
    file_extension: Optional[str] = None
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    category: str
    tag: Optional[str] = None
    source_type: Optional[str] = None
    file_url: Optional[str] = None
    s3_key: str
    version: int
    is_latest: bool
    metadata_json: Optional[Any] = None
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None

    versions: List[CaseDocumentVersionOut] = []
    audit_logs: List[CaseDocumentAuditLogOut] = []

    model_config = ConfigDict(from_attributes=True)


class ShareLinkOut(BaseModel):
    url: str
    expires_in_seconds: int