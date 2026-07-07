from fastapi import APIRouter, UploadFile, File, Depends
from appflow.services.s3_service import s3_service
from appflow.models.s3_model import DocumentMetadata, CaseDocumentsResponse
from typing import List
from datetime import datetime

router = APIRouter(prefix="/documents", tags=["S3 Document Library"])

@router.post("/upload/{case_id}", response_model=DocumentMetadata)
async def upload_file(
    case_id: str, 
    category: str, 
    uploaded_by: str, 
    file: UploadFile = File(...)
):
    # Requirement: Automatically push files to S3 [cite: 7]
    s3_key = await s3_service.upload_document(file, case_id, category, uploaded_by)
    preview_url = s3_service.get_presigned_url(s3_key)
    
    return {
        "file_name": file.filename,
        "s3_key": s3_key,
        "category": category,
        "uploaded_by": uploaded_by,
        "upload_date": datetime.now(),
        "preview_url": preview_url
    }

@router.get("/case/{case_id}", response_model=CaseDocumentsResponse)
async def get_case_documents(case_id: str):
    # Requirement: Fetch all files by caseId and display them dynamically 
    # In a real app, you would fetch these references from your Database
    pass