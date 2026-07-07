from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class DocumentMetadata(BaseModel):
    file_name: str
    s3_key: str
    category: str
    uploaded_by: str
    upload_date: datetime
    preview_url: Optional[str] = None

class CaseDocumentsResponse(BaseModel):
    case_id: str
    documents: List[DocumentMetadata]