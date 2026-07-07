from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class CaseActivityAttachmentOut(BaseModel):
    file_name: str
    file_url: str
    file_size: Optional[str] = ""
    case_document_id: Optional[int] = None

class CaseNoteCreate(BaseModel):
    note: str
    created_by: Optional[str] = None

class CaseNoteReplyCreate(BaseModel):
    reply: str


class CaseActivityNoteReplyOut(BaseModel):
    id: Union[int, str]
    noteId: Union[int, str]
    text: str

    createdAt: Optional[datetime] = None

    createdById: Optional[Union[int, str]] = None
    createdByName: Optional[str] = ""
    createdByRole: Optional[str] = ""

    class Config:
        orm_mode = True


class CaseActivityNoteOut(BaseModel):
    id: Union[int, str]

    activityId: Union[int, str]

    text: str

    createdAt: Optional[datetime] = None

    createdById: Optional[Union[int, str]] = None
    createdByName: Optional[str] = ""
    createdByRole: Optional[str] = ""

    replies: List[CaseActivityNoteReplyOut] = Field(
        default_factory=list
    )

    class Config:
        orm_mode = True


class CaseActivityItemOut(BaseModel):
    id: Union[int, str]
    type: str
    history_file_type: Optional[str] = ""
    title: str
    timestamp: Optional[datetime] = None
    claim_reference: Optional[str] = ""
    summary: Optional[str] = ""
    detail_text: Optional[str] = ""
    created_by_name: Optional[str] = ""
    attachments: List[CaseActivityAttachmentOut] = Field(default_factory=list)

    subject: Optional[str] = ""
    sender_name: Optional[str] = ""
    sender_email: Optional[str] = ""
    received_at: Optional[datetime] = None
    body_preview: Optional[str] = ""
    body_text: Optional[str] = ""
    body_html: Optional[str] = ""

    meta: Dict[str, Any] = Field(default_factory=dict)