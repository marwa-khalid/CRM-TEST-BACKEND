from pydantic import BaseModel
from typing import Optional,List
from datetime import datetime
from libdata.enums import HistoryLogType
from urllib.parse import quote


class HistoryActivityBase(BaseModel):
    file_name: Optional[str] = None
    file_path: str
    claim_id: int
    file_type: HistoryLogType


class HistoryActivityIn(HistoryActivityBase):
    pass

# class HistoryActivityOut(HistoryActivityBase):
#     id: int
#     created_at: datetime
#     updated_at: datetime
#     created_by: Optional[int] = None
#     updated_by: Optional[int] = None
#
#     class Config:
#         from_attributes = True

# class HistoryActivityOut(HistoryActivityBase):
#     id: int
#     created_at: datetime
#     updated_at: datetime
#     created_by_name: Optional[str] = None
#     updated_by: Optional[int] = None
#     url: Optional[str] = None   # ✅ new
#
#     class Config:
#         from_attributes = True
#
#     @classmethod
#     def from_orm_with_url(cls, row, request):
#         history, created_by_name = row
#
#         instance = super().from_orm(history)
#         instance.created_by_name = created_by_name
#
#         base_url = str(request.base_url).rstrip("/")
#
#         # Encode file path safely
#         safe_file_path = quote(instance.file_path)
#
#         # if instance.file_type == HistoryLogType.ENGINEER_DETAIL:
#         #     instance.url = f"{base_url}:9000/uploads/history{safe_file_path}"
#         # else:
#         #     instance.url = ""
#
#         if instance.file_type == HistoryLogType.ENGINEER_DETAIL:
#             instance.url = f"{base_url}:9000/uploads/history{safe_file_path}"
#         elif instance.file_type == HistoryLogType.HISTORYUPLOAD:
#             instance.url = f"{base_url}:9000/uploads/history/{safe_file_path}"
#         else:
#             instance.url = ""
#
#         return instance

class HistoryActivityOut(HistoryActivityBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    urls: Optional[List[str]] = None  # ✅ Changed to list of URLs

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_url(cls, row, request):
        history, created_by_name = row

        instance = super().from_orm(history)
        instance.created_by_name = created_by_name

        base_url = str(request.base_url).rstrip("/")
        instance.urls = []  # Initialize as empty list

        # Handle different file types
        if not instance.file_path or instance.file_path.strip() == "":
            instance.urls = []
        elif instance.file_type == HistoryLogType.ENGINEER_DETAIL:
            # For single engineer detail files
            safe_file_path = quote(instance.file_path)
            url = f"{base_url}:9000/uploads/history{safe_file_path}"
            instance.urls = [url]
        elif instance.file_type == HistoryLogType.HISTORYUPLOAD:
            # For history upload files
            safe_file_path = quote(instance.file_path)
            url = f"{base_url}:9000/uploads/history/{safe_file_path}"
            instance.urls = [url]
        elif instance.file_type == HistoryLogType.AI_REPORT:
            # For AI reports with multiple image URLs (comma-separated)
            if instance.file_path and instance.file_path.strip():
                # Split by comma and clean up whitespace
                file_paths = [path.strip() for path in instance.file_path.split(',')]
                instance.urls = file_paths  # Return the Cloudinary URLs directly
        else:
            instance.urls = []

        return instance