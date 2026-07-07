import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse
import io
import shutil
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastapi import HTTPException, UploadFile, status

load_dotenv()


class S3Service:
    def __init__(self):
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME", "crm-nationwide-assist")
        self.region = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")

        self.client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=self.region,
            # Auto-retry transient network blips (e.g. a momentary
            # EndpointConnectionError to eu-north-1) so a single hiccup doesn't
            # surface as a 500 (e.g. document-preview render failures).
            config=Config(
                retries={"max_attempts": 5, "mode": "adaptive"},
                connect_timeout=10,
                read_timeout=30,
            ),
        )

    def upload_driver_document(self, file: UploadFile, claim_id: int, field_name: str) -> str:
        allowed_extensions = {".jpg", ".jpeg", ".png", ".pdf"}
        extension = Path(file.filename or "").suffix.lower()

        if extension not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only JPG, JPEG, PNG, and PDF files are allowed.",
            )

        safe_field = field_name.strip().lower()
        unique_name = f"{uuid.uuid4().hex}{extension}"
        s3_key = f"claims/{claim_id}/driver-documents/{safe_field}/{unique_name}"

        try:
            file.file.seek(0)
            self.client.upload_fileobj(
                Fileobj=file.file,
                Bucket=self.bucket_name,
                Key=s3_key,
                ExtraArgs={
                    "ContentType": file.content_type or "application/octet-stream"
                },
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to S3: {str(exc)}",
            )

        return {
            "s3_key": s3_key,
            "file_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        }
    
    def upload_ai_report_pdf(
        self,
        pdf_bytes: bytes,
        claim_id: int,
        file_name: str | None = None,
    ) -> dict:
        unique_name = (
            file_name
            or f"{uuid.uuid4().hex}_AI_Damage_Report.pdf"
        )

        s3_key = f"claims/{claim_id}/ai-reports/{unique_name}"

        try:
            pdf_buffer = io.BytesIO(pdf_bytes)

            self.client.upload_fileobj(
                Fileobj=pdf_buffer,
                Bucket=self.bucket_name,
                Key=s3_key,
                ExtraArgs={
                    "ContentType": "application/pdf"
                },
            )

        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload AI PDF to S3: {str(exc)}",
            )

        return {
            "s3_key": s3_key,
            "file_url": (
                f"https://{self.bucket_name}.s3."
                f"{self.region}.amazonaws.com/{s3_key}"
            ),
        }
    def upload_case_document(self, file: UploadFile, claim_id: int, category: str) -> dict:
        extension = Path(file.filename or "").suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{extension}"
        safe_category = category.lower().replace(" ", "-")
        s3_key = f"claims/{claim_id}/documents/{safe_category}/{unique_name}"

        try:
            file.file.seek(0)
            self.client.upload_fileobj(
                Fileobj=file.file,
                Bucket=self.bucket_name,
                Key=s3_key,
                ExtraArgs={
                    "ContentType": file.content_type or "application/octet-stream"
                },
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload case document to S3: {str(exc)}",
            )

        file_url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"

        return {
            "s3_key": s3_key,
            "file_url": file_url,
            "storage_backend": "s3",
        }

    @staticmethod
    def local_upload_public_path(path: str | None) -> str:
        if not path:
            return ""

        parsed = urlparse(str(path))
        raw_path = parsed.path if parsed.scheme in {"http", "https"} else str(path)
        normalized = raw_path.replace("\\", "/")

        uploads_marker = "/uploads/"
        uploads_index = normalized.find(uploads_marker)
        if uploads_index >= 0:
            return normalized[uploads_index:]

        if normalized.startswith("uploads/"):
            return f"/{normalized}"

        return normalized if normalized.startswith("/") else f"/{normalized}"

    @staticmethod
    def is_local_upload_key(key: str | None) -> bool:
        public_path = S3Service.local_upload_public_path(key)
        return public_path.startswith("/uploads/")

    @staticmethod
    def local_upload_filesystem_path(key: str | None) -> str:
        public_path = S3Service.local_upload_public_path(key)
        if not public_path.startswith("/uploads/"):
            return ""

        relative_path = public_path.removeprefix("/uploads/").lstrip("/")
        return str(Path(os.getcwd()) / "uploads" / relative_path)

    def _local_upload_result(self, local_path: str, exc: Exception | None = None) -> dict:
        import shutil

        public_path = self.local_upload_public_path(local_path)
        if not public_path.startswith("/uploads/"):
            public_path = f"/uploads/{os.path.basename(str(local_path or '')) or public_path.lstrip('/')}"

        # StaticFiles serves {cwd}/uploads. If the fallback file lives outside that
        # dir (e.g. a temp path), copy it in so the /uploads/... URL resolves
        # instead of returning 404.
        served_root = os.path.join(os.getcwd(), "uploads")
        rel = public_path.removeprefix("/uploads/").lstrip("/")
        dest = os.path.join(served_root, rel)
        try:
            if (
                local_path
                and os.path.exists(str(local_path))
                and os.path.abspath(str(local_path)) != os.path.abspath(dest)
            ):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(str(local_path), dest)
        except Exception:
            pass

        result = {
            "s3_key": public_path,
            "file_url": public_path,
            "storage_backend": "local",
        }

        if exc:
            result["storage_error"] = str(exc)

        return result

    def upload_case_document_with_fallback(
        self,
        file: UploadFile,
        claim_id: int,
        category: str,
        fallback_local_path: str | None = None,
    ) -> dict:
        try:
            return self.upload_case_document(file=file, claim_id=claim_id, category=category)
        except HTTPException as exc:
            if not fallback_local_path:
                raise
            print(f"Case document S3 upload failed; using local fallback: {exc}")
            return self._local_upload_result(fallback_local_path, exc)

    def upload_task_attachment(self, file: UploadFile) -> dict:
        """Upload a Task attachment to S3 (durable, unlike the local disk)."""
        name = Path(file.filename or "file").name
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "file"
        # Stored under the `claims/` prefix because the IAM policy only grants
        # s3:PutObject there (a dedicated tasks/ prefix is denied).
        s3_key = f"claims/task-attachments/{uuid.uuid4().hex}/{safe}"

        try:
            file.file.seek(0)
            self.client.upload_fileobj(
                Fileobj=file.file,
                Bucket=self.bucket_name,
                Key=s3_key,
                ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload task attachment to S3: {str(exc)}",
            )

        return {
            "s3_key": s3_key,
            "file_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}",
        }

    def upload_task_attachment_local(self, file: UploadFile) -> dict:
        """Store a Task attachment under the mounted /uploads directory."""
        name = Path(file.filename or "file").name
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "file"
        folder = f"{uuid.uuid4().hex}"
        target_dir = Path(os.getcwd()) / "uploads" / "task-attachments" / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe

        try:
            file.file.seek(0)
            with target_path.open("wb") as out:
                shutil.copyfileobj(file.file, out)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save task attachment locally: {str(exc)}",
            )

        public_path = f"/uploads/task-attachments/{folder}/{safe}"
        return {
            "s3_key": public_path,
            "file_url": public_path,
        }

    def upload_task_attachment_with_fallback(self, file: UploadFile) -> dict:
        """Prefer S3, but fall back to local uploads if S3 is unavailable."""
        try:
            return self.upload_task_attachment(file)
        except HTTPException:
            return self.upload_task_attachment_local(file)

    def read_file_bytes(self, s3_key: str) -> bytes:
        """Return the raw bytes for a stored file, whether it lives on the local
        uploads disk or in S3."""
        if self.is_local_upload_key(s3_key):
            path = self.local_upload_filesystem_path(s3_key)
            with open(path, "rb") as f:
                return f.read()
        obj = self.client.get_object(Bucket=self.bucket_name, Key=s3_key)
        return obj["Body"].read()

    def generate_presigned_url(self, s3_key: str, expires_in: int = 604800) -> str:
        if self.is_local_upload_key(s3_key):
            return self.local_upload_public_path(s3_key)

        return self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": s3_key,
                "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": "inline",
            },
            ExpiresIn=expires_in,
        )
    
    def generate_presigned_download_url(
        self,
        s3_key: str,
        expires_in_seconds: int = 3600,
        force_download: bool = False,
    ) -> str:
        if self.is_local_upload_key(s3_key):
            return self.local_upload_public_path(s3_key)

        try:
            params = {
                "Bucket": self.bucket_name,
                "Key": s3_key,
            }
            if force_download:
                filename = (s3_key.rsplit("/", 1)[-1] or "download").replace('"', "")
                params["ResponseContentDisposition"] = (
                    f'attachment; filename="{filename}"'
                )

            return self.client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate presigned URL: {str(exc)}",
            )

    def upload_ai_report_pdf_bytes(self, pdf_bytes: bytes, claim_id: int, file_name: str) -> dict:
        unique_name = f"{uuid.uuid4().hex}_{file_name}"
        s3_key = f"claims/{claim_id}/ai-reports/{unique_name}"

        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload AI PDF to S3: {str(exc)}",
            )

        return {
            "s3_key": s3_key,
            "file_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        }

    def upload_ai_image_bytes(self, image_bytes: bytes, claim_id: int, filename: str, category: str = "ai-annotated-images") -> dict:
        extension = Path(filename or "").suffix.lower() or ".jpg"
        unique_name = f"{uuid.uuid4().hex}{extension}"
        safe_category = category.lower().replace(" ", "-")
        s3_key = f"claims/{claim_id}/documents/{safe_category}/{unique_name}"

        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=image_bytes,
                ContentType="image/jpeg" if extension in [".jpg", ".jpeg"] else "image/png",
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload annotated image to S3: {str(exc)}",
            )

        return {
            "s3_key": s3_key,
            "file_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}",
        }


    def upload_witness_questionnaire_pdf_bytes(
        self,
        pdf_bytes: bytes,
        claim_id: int,
        filename: str = "Witness-Questionnaire.pdf",
    ) -> dict:
        safe_filename = filename.replace("/", "_").replace("..", "_")
        unique_name = f"{uuid.uuid4().hex}_{safe_filename}"
        s3_key = f"claims/{claim_id}/documents/witness-questionnaires/{unique_name}"

        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload witness questionnaire PDF to S3: {str(exc)}",
            )

        return {
            "s3_key": s3_key,
            "file_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}",
        }

    def upload_claim_document_bytes(
        self,
        file_bytes: bytes,
        claim_id: int,
        filename: str,
        folder: str = "uploads",
        content_type: str = "application/octet-stream",
    ):
        import uuid
        import urllib.parse

        safe_filename = filename.replace("/", "_").replace("..", "_")
        unique_filename = f"{uuid.uuid4().hex}_{safe_filename}"

        s3_key = f"claims/{claim_id}/documents/{folder}/{unique_filename}"

        self.client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
        )

        file_url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{urllib.parse.quote(s3_key)}"

        return {
            "s3_key": s3_key,
            "file_url": file_url,
            "storage_backend": "s3",
        }

    def upload_claim_document_bytes_with_fallback(
        self,
        file_bytes: bytes,
        claim_id: int,
        filename: str,
        folder: str = "uploads",
        content_type: str = "application/octet-stream",
        fallback_local_path: str | None = None,
    ) -> dict:
        try:
            return self.upload_claim_document_bytes(
                file_bytes=file_bytes,
                claim_id=claim_id,
                filename=filename,
                folder=folder,
                content_type=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            if not fallback_local_path:
                raise
            print(f"Claim document S3 upload failed; using local fallback: {exc}")
            return self._local_upload_result(fallback_local_path, exc)

    def upload_claim_image_bytes(self, image_bytes: bytes, claim_id: int, filename: str, category: str = "ai-images") -> dict:
        extension = Path(filename or "").suffix.lower() or ".jpg"
        unique_name = f"{uuid.uuid4().hex}{extension}"
        safe_category = category.lower().replace(" ", "-")
        s3_key = f"claims/{claim_id}/documents/{safe_category}/{unique_name}"

        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=image_bytes,
                ContentType="image/jpeg" if extension in [".jpg", ".jpeg"] else "image/png",
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload claim image to S3: {str(exc)}",
            )

        return {
            "s3_key": s3_key,
            "file_url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        }
