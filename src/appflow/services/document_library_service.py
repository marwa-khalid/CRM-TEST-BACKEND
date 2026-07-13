import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, UploadFile, status
import base64
import csv
from io import BytesIO, StringIO
import fitz
from libdata.models.tables import CaseDocument, CaseDocumentAuditLog, Claim
from appflow.services.s3_service import S3Service
from appflow.services.history_activity_service import HistoryActivityService
import mimetypes
import boto3
from botocore.config import Config
from libdata.enums import HistoryLogType
class DocumentLibraryService:
    @staticmethod
    def _preview_png_bytes(pixmap, compact: bool = False) -> bytes:
        image_bytes = pixmap.tobytes("png")
        if not compact:
            return image_bytes

        try:
            from PIL import Image

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            width, height = image.size
            pixels = image.load()
            threshold = 248

            def row_has_content(y: int) -> bool:
                for x in range(width):
                    r, g, b = pixels[x, y]
                    if r < threshold or g < threshold or b < threshold:
                        return True
                return False

            top = 0
            while top < height and not row_has_content(top):
                top += 1

            if top >= height:
                return image_bytes

            bottom = height - 1
            while bottom > top and not row_has_content(bottom):
                bottom -= 1

            padding = 2
            top = max(0, top - padding)
            bottom = min(height - 1, bottom + padding)

            if top == 0 and bottom == height - 1:
                return image_bytes

            cropped = image.crop((0, top, width, bottom + 1))
            output = BytesIO()
            cropped.save(output, format="PNG", optimize=True)
            return output.getvalue()
        except Exception as error:
            print("Compact PDF preview crop failed:", str(error))
            return image_bytes

    @staticmethod
    def _combine_preview_pngs(image_bytes_list: list[bytes]) -> bytes:
        if not image_bytes_list:
            return b""
        if len(image_bytes_list) == 1:
            return image_bytes_list[0]

        try:
            from PIL import Image

            images = [
                Image.open(BytesIO(image_bytes)).convert("RGB")
                for image_bytes in image_bytes_list
            ]
            max_width = max(image.width for image in images)
            total_height = sum(image.height for image in images)

            combined = Image.new("RGB", (max_width, total_height), "white")
            y_offset = 0
            for image in images:
                x_offset = (max_width - image.width) // 2
                combined.paste(image, (x_offset, y_offset))
                y_offset += image.height

            output = BytesIO()
            combined.save(output, format="PNG", optimize=True)
            return output.getvalue()
        except Exception as error:
            print("Compact PDF preview combine failed:", str(error))
            return image_bytes_list[0]

    @staticmethod
    def list_case_documents(claim_id: int, db: Session):
        return (
            db.query(CaseDocument)
            .filter(
                CaseDocument.claim_id == claim_id,
                CaseDocument.is_active == True,
                CaseDocument.is_deleted == False,
                CaseDocument.is_latest == True,
            )
            .order_by(CaseDocument.created_at.desc())
            .all()
        )

    @staticmethod
    def list_all_documents(db: Session, tenant_id: int | None = None):
        from libdata.models.tables import CaseDocument

        return (
            db.query(CaseDocument)
            .filter(CaseDocument.is_deleted == False)
            .order_by(CaseDocument.created_at.desc())
            .all()
        )
    @staticmethod
    def get_document_preview_pages(document_id: int, db: Session, compact: bool = False):
        document = (
            db.query(CaseDocument)
            .filter(
                CaseDocument.id == document_id,
                CaseDocument.is_active == True,
                CaseDocument.is_deleted == False,
            )
            .first()
        )

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        file_extension = (document.file_extension or "").lower().replace(".", "")
        content_type = (document.content_type or "").lower()
        file_name = (document.file_name or "").lower()

        is_image = (
            content_type.startswith("image/")
            or file_extension in ["jpg", "jpeg", "png", "webp", "gif", "svg"]
        )

        is_csv = (
            file_extension == "csv"
            or file_name.endswith(".csv")
            or "csv" in content_type
            or content_type in [
                "text/plain",
                "application/vnd.ms-excel",
                "application/octet-stream",
            ]
        )

        is_pdf = "pdf" in content_type or file_extension == "pdf"

        local_path = S3Service.local_upload_filesystem_path(document.s3_key)
        if local_path:
            if not os.path.exists(local_path):
                raise HTTPException(status_code=404, detail="Local fallback file not found")

            if is_image:
                mime_type = mimetypes.guess_type(local_path)[0] or content_type or "application/octet-stream"
                with open(local_path, "rb") as image_file:
                    image_base64 = base64.b64encode(image_file.read()).decode("utf-8")

                return {
                    "type": "image",
                    "url": f"data:{mime_type};base64,{image_base64}",
                    "file_name": document.file_name,
                }

            if is_pdf:
                try:
                    with open(local_path, "rb") as pdf_file:
                        pdf_bytes = pdf_file.read()

                    pdf_document = fitz.open(
                        stream=pdf_bytes,
                        filetype="pdf",
                    )

                    pages = []
                    compact_page_images = []

                    for page_index in range(len(pdf_document)):
                        page = pdf_document.load_page(page_index)
                        pixmap = page.get_pixmap(
                            matrix=fitz.Matrix(1.35, 1.35),
                            alpha=False,
                        )
                        image_bytes = DocumentLibraryService._preview_png_bytes(
                            pixmap,
                            compact=compact,
                        )
                        if compact:
                            compact_page_images.append(image_bytes)
                            continue

                        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                        pages.append(
                            {
                                "page": page_index + 1,
                                "image": f"data:image/png;base64,{image_base64}",
                            }
                        )

                    if compact and compact_page_images:
                        image_base64 = base64.b64encode(
                            DocumentLibraryService._combine_preview_pngs(
                                compact_page_images,
                            )
                        ).decode("utf-8")
                        pages = [
                            {
                                "page": 1,
                                "image": f"data:image/png;base64,{image_base64}",
                            }
                        ]

                    pdf_document.close()

                    return {
                        "type": "pdf",
                        "file_name": document.file_name,
                        "pages": pages,
                    }

                except Exception as error:
                    print("Local PDF preview render failed:", str(error))
                    raise HTTPException(
                        status_code=500,
                        detail="Unable to render PDF preview",
                    )

            return {
                "type": "unsupported",
                "message": "Preview is not available for this file type.",
            }

        s3_service = S3Service()
        bucket_name = s3_service.bucket_name
        s3_client = s3_service.client

        if is_image:
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket_name,
                    "Key": document.s3_key,
                },
                ExpiresIn=3600,
            )

            return {
                "type": "image",
                "url": url,
                "file_name": document.file_name,
            }

        if is_csv:
            try:
                s3_object = s3_client.get_object(
                    Bucket=bucket_name,
                    Key=document.s3_key,
                )

                csv_bytes = s3_object["Body"].read()

                try:
                    csv_text = csv_bytes.decode("utf-8-sig")
                except UnicodeDecodeError:
                    csv_text = csv_bytes.decode("latin-1")

                csv_reader = csv.reader(StringIO(csv_text))
                rows = list(csv_reader)

                if not rows:
                    return {
                        "type": "csv",
                        "file_name": document.file_name,
                        "headers": [],
                        "rows": [],
                        "total_rows": 0,
                        "preview_rows": 0,
                    }

                max_columns = max(len(row) for row in rows)

                normalized_rows = [
                    row + [""] * (max_columns - len(row))
                    for row in rows
                ]

                headers = normalized_rows[0]
                body_rows = normalized_rows[1:101]

                return {
                    "type": "csv",
                    "file_name": document.file_name,
                    "headers": headers,
                    "rows": body_rows,
                    "total_rows": max(len(normalized_rows) - 1, 0),
                    "preview_rows": len(body_rows),
                }

            except Exception as error:
                print("CSV preview failed:", str(error))
                raise HTTPException(
                    status_code=500,
                    detail="Unable to render CSV preview",
                )

        if is_pdf:
            try:
                s3_object = s3_client.get_object(
                    Bucket=bucket_name,
                    Key=document.s3_key,
                )

                pdf_bytes = s3_object["Body"].read()

                pdf_document = fitz.open(
                    stream=pdf_bytes,
                    filetype="pdf",
                )

                pages = []
                compact_page_images = []

                for page_index in range(len(pdf_document)):
                    page = pdf_document.load_page(page_index)

                    zoom = 1.35
                    matrix = fitz.Matrix(zoom, zoom)

                    pixmap = page.get_pixmap(
                        matrix=matrix,
                        alpha=False,
                    )

                    image_bytes = DocumentLibraryService._preview_png_bytes(
                        pixmap,
                        compact=compact,
                    )
                    if compact:
                        compact_page_images.append(image_bytes)
                        continue

                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                    pages.append(
                        {
                            "page": page_index + 1,
                            "image": f"data:image/png;base64,{image_base64}",
                        }
                    )

                if compact and compact_page_images:
                    image_base64 = base64.b64encode(
                        DocumentLibraryService._combine_preview_pngs(
                            compact_page_images,
                        )
                    ).decode("utf-8")
                    pages = [
                        {
                            "page": 1,
                            "image": f"data:image/png;base64,{image_base64}",
                        }
                    ]

                pdf_document.close()

                return {
                    "type": "pdf",
                    "file_name": document.file_name,
                    "pages": pages,
                }

            except Exception as error:
                print("PDF preview render failed:", str(error))
                raise HTTPException(
                    status_code=500,
                    detail="Unable to render PDF preview",
                )

        return {
            "type": "unsupported",
            "message": "Preview is not available for this file type.",
        }
    @staticmethod
    def get_upload_file_size(file: UploadFile):
        try:
            current_position = file.file.tell()
            file.file.seek(0, os.SEEK_END)
            size = file.file.tell()
            file.file.seek(current_position)
            return size
        except Exception:
            return getattr(file, "size", None)
            
    
    @staticmethod
    def send_documents_email(to: str, cc: str, subject: str, body: str, attachments: list):
        """Email the selected document-library files as real attachments.

        Files are read from local uploads or S3 and attached to the message.
        Sends via Microsoft Graph (from the connected Outlook mailbox) with a
        SendGrid fallback."""
        from appflow.services.graph_email_service import GraphEmailService
        from appflow.logger import logger

        recipients = [e.strip() for e in str(to or "").replace(",", ";").split(";") if e.strip() and "@" in e]
        if not recipients:
            raise HTTPException(status_code=400, detail="At least one valid recipient is required")

        s3 = S3Service()
        email_atts = []
        for att in (attachments or []):
            s3_key = (att or {}).get("s3_key")
            if not s3_key:
                continue
            try:
                raw = s3.read_file_bytes(s3_key)
            except Exception as exc:
                logger.warning(f"send_documents_email: could not read {s3_key}: {exc}")
                continue
            name = att.get("file_name") or str(s3_key).split("/")[-1]
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            email_atts.append({
                "name": name,
                "content_bytes": base64.b64encode(raw).decode(),
                "content_type": ctype,
            })

        if not email_atts:
            raise HTTPException(status_code=400, detail="None of the selected files could be attached")

        subject = subject or "Documents from Nationwide Assist"
        safe_body = (body or "").replace("\n", "<br>")
        html = (
            "<div style=\"font-family:Arial,sans-serif;font-size:14px;color:#334155;\">"
            f"{safe_body or 'Please find the attached documents.'}"
            "</div>"
        )

        # Prefer Microsoft Graph (delivered from a real Outlook mailbox).
        if GraphEmailService.is_configured():
            result = GraphEmailService.send_mail(
                recipients, subject, html, cc=cc, attachments=email_atts
            )
            if result is not None:
                return {"status": "sent", "via": "graph", "attachments": len(email_atts)}
            logger.warning("Graph send failed for document email; falling back to SendGrid")

        # SendGrid fallback.
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import (
                Mail, Attachment, FileContent, FileName, FileType, Disposition,
            )
            api_key = os.getenv("SENDGRID_API_KEY")
            if not api_key:
                raise HTTPException(status_code=500, detail="Email is not configured")
            message = Mail(
                from_email=os.getenv("SENDGRID_SENDER", "no-replynationwideassist@outlook.com"),
                to_emails=recipients,
                subject=subject,
                html_content=html,
            )
            for att in email_atts:
                message.add_attachment(Attachment(
                    FileContent(att["content_bytes"]),
                    FileName(att["name"]),
                    FileType(att["content_type"]),
                    Disposition("attachment"),
                ))
            resp = SendGridAPIClient(api_key).send(message)
            return {"status": "sent", "via": "sendgrid", "sendgrid_status": resp.status_code,
                    "attachments": len(email_atts)}
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(f"send_documents_email failed: {exc}")
            raise HTTPException(status_code=502, detail="Failed to send email")

    @staticmethod
    def list_claim_photos(claim_id: int, db: Session):
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        region_name = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")

        if not bucket_name:
            raise HTTPException(
                status_code=500,
                detail="AWS_S3_BUCKET_NAME is not configured",
            )

        s3_client = boto3.client(
            "s3",
            region_name=region_name,
            config=Config(signature_version="s3v4"),
        )

        folders = [
            {
                "type": "Original",
                "prefix": f"claims/{claim_id}/documents/ai-images/",
            },
            {
                "type": "Annotated",
                "prefix": f"claims/{claim_id}/documents/ai-annotated-images/",
            },
        ]

        allowed_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif")
        photos = []

        for folder in folders:
            continuation_token = None

            while True:
                params = {
                    "Bucket": bucket_name,
                    "Prefix": folder["prefix"],
                }

                if continuation_token:
                    params["ContinuationToken"] = continuation_token

                response = s3_client.list_objects_v2(**params)

                for item in response.get("Contents", []):
                    s3_key = item.get("Key")

                    if not s3_key:
                        continue

                    if s3_key.endswith("/"):
                        continue

                    if not s3_key.lower().endswith(allowed_extensions):
                        continue

                    file_name = s3_key.split("/")[-1]

                    presigned_url = s3_client.generate_presigned_url(
                        "get_object",
                        Params={
                            "Bucket": bucket_name,
                            "Key": s3_key,
                        },
                        ExpiresIn=3600,
                    )

                    photos.append(
                        {
                            "id": s3_key,
                            "file_name": file_name,
                            "file_url": presigned_url,
                            "s3_key": s3_key,
                            "category": "Photos",
                            "photo_type": folder["type"],
                            "content_type": mimetypes.guess_type(file_name)[0]
                            or "image/jpeg",
                            "file_size_bytes": item.get("Size"),
                            "created_at": item.get("LastModified").isoformat()
                            if item.get("LastModified")
                            else None,
                        }
                    )

                if response.get("IsTruncated"):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    break

        photos.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return photos

    @staticmethod
    def get_document_detail(document_id: int, db: Session):
        document = (
            db.query(CaseDocument)
            .options(joinedload(CaseDocument.audit_logs))
            .filter(
                CaseDocument.id == document_id,
                CaseDocument.is_active == True,
                CaseDocument.is_deleted == False,
            )
            .first()
        )

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        root_id = document.parent_document_id or document.id

        versions = (
            db.query(CaseDocument)
            .filter(
                CaseDocument.is_active == True,
                CaseDocument.is_deleted == False,
                (
                    (CaseDocument.id == root_id)
                    | (CaseDocument.parent_document_id == root_id)
                ),
            )
            .order_by(CaseDocument.version.desc())
            .all()
        )

        document.versions = versions
        return document

    @staticmethod
    def upload_document(
        claim_id: int,
        category: str,
        tag: str,
        source_type: str,
        file: UploadFile,
        db: Session,
        user_id: int,
        tenant_id: int,
    ):
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        s3_service = S3Service()
        upload_result = s3_service.upload_case_document(
            file=file,
            claim_id=claim_id,
            category=category,
        )

        original_filename = file.filename or "document"
        file_extension = os.path.splitext(original_filename)[1].lower().replace(".", "")
        content_type = file.content_type
        logical_name = original_filename

        existing_latest = (
            db.query(CaseDocument)
            .filter(
                CaseDocument.claim_id == claim_id,
                CaseDocument.file_name == logical_name,
                CaseDocument.category == category,
                CaseDocument.is_latest == True,
                CaseDocument.is_deleted == False,
            )
            .first()
        )
        now = datetime.now(timezone.utc)
        file_size_bytes = DocumentLibraryService.get_upload_file_size(file)

        try:
            file.file.seek(0)
        except Exception:
            pass

        version = 1
        parent_document_id = None

        if existing_latest:
            existing_latest.is_latest = False
            existing_latest.updated_by = user_id
            existing_latest.updated_at = datetime.utcnow()

            version = (existing_latest.version or 1) + 1
            parent_document_id = existing_latest.parent_document_id or existing_latest.id

        document = CaseDocument(
            claim_id=claim_id,
            file_name=logical_name,
            original_filename=original_filename,
            file_extension=file_extension,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            created_at=now,
            updated_at=now,
            category=category,
            tag=tag,
            source_type=source_type,
            s3_key=upload_result["s3_key"],
            file_url=upload_result["file_url"],
            version=version,
            parent_document_id=parent_document_id,
            is_latest=True,
            created_by=user_id,
            updated_by=user_id,
            tenant_id=tenant_id,
            metadata_json={
                "case_reference": None,
            },
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        audit = CaseDocumentAuditLog(
            case_document_id=document.id,
            action="upload" if version == 1 else "version_upload",
            action_detail=f"{logical_name} uploaded to category {category}",
            created_by=user_id,
            updated_by=user_id,
            # tenant_id=tenant_id,
        )
        db.add(audit)
        db.commit()

        HistoryActivityService.create_activity(
            db=db,
            claim_id=claim_id,
            file_name=f"{logical_name} uploaded to Document Library",
            file_path=upload_result["file_url"],
            file_type=HistoryLogType.HISTORYUPLOAD,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        return document

    @staticmethod
    def create_share_link(document_id: int, expires_in_seconds: int, db: Session, user_id: int, tenant_id: int):
        document = (
            db.query(CaseDocument)
            .filter(
                CaseDocument.id == document_id,
                CaseDocument.is_active == True,
                CaseDocument.is_deleted == False,
            )
            .first()
        )
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        s3_service = S3Service()
        url = s3_service.generate_presigned_download_url(
            s3_key=document.s3_key,
            expires_in_seconds=expires_in_seconds,
        )

        audit = CaseDocumentAuditLog(
            case_document_id=document.id,
            action="share",
            action_detail=f"Presigned share link generated for {expires_in_seconds} seconds",
            created_by=user_id,
            updated_by=user_id,
            # tenant_id=tenant_id,
        )
        db.add(audit)
        db.commit()

        return {
            "url": url,
            "expires_in_seconds": expires_in_seconds,
        }

    @staticmethod
    def register_preview(document_id: int, db: Session, user_id: int, tenant_id: int):
        document = db.query(CaseDocument).filter(CaseDocument.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        audit = CaseDocumentAuditLog(
            case_document_id=document.id,
            action="preview",
            action_detail=f"Previewed {document.file_name}",
            created_by=user_id,
            updated_by=user_id,
            # tenant_id=tenant_id,
        )
        db.add(audit)
        db.commit()
        return {"message": "Preview logged"}

    @staticmethod
    def register_download(document_id: int, db: Session, user_id: int, tenant_id: int):
        document = db.query(CaseDocument).filter(CaseDocument.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        audit = CaseDocumentAuditLog(
            case_document_id=document.id,
            action="download",
            action_detail=f"Downloaded {document.file_name}",
            created_by=user_id,
            updated_by=user_id,
            # tenant_id=tenant_id,
        )
        db.add(audit)
        db.commit()
        return {"message": "Download logged"}

    @staticmethod
    def get_presigned_file_url(
        document_id: int,
        db: Session,
        base_url: str | None = None,
        download: bool = False,
    ):
        document = (
            db.query(CaseDocument)
            .filter(
                CaseDocument.id == document_id,
                CaseDocument.is_active == True,
                CaseDocument.is_deleted == False,
            )
            .first()
        )
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        s3_service = S3Service()
        if S3Service.is_local_upload_key(document.s3_key):
            public_path = S3Service.local_upload_public_path(document.file_url or document.s3_key)
            if base_url:
                return {"url": f"{base_url.rstrip('/')}{public_path}"}
            return {"url": public_path}

        if download:
            download_name = (
                document.original_filename
                or document.file_name
                or "document.pdf"
            ).replace('"', "")
            url = s3_service.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": s3_service.bucket_name,
                    "Key": document.s3_key,
                    "ResponseContentDisposition": f'attachment; filename="{download_name}"',
                    "ResponseContentType": document.content_type
                    or "application/octet-stream",
                },
                ExpiresIn=3600,
            )
        else:
            url = s3_service.generate_presigned_download_url(
                s3_key=document.s3_key,
                expires_in_seconds=3600,
            )

        return {"url": url}
