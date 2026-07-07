from __future__ import annotations

from tempfile import SpooledTemporaryFile
from typing import Iterable, List

from fastapi import UploadFile
from starlette.datastructures import Headers

from appflow.services.import_job_service import FilePayload


async def serialize_uploads(files: Iterable[UploadFile]) -> List[FilePayload]:
    payloads: List[FilePayload] = []
    for file in files:
        data = await file.read()
        payloads.append(
            FilePayload(
                filename=file.filename or "file.bin",
                content_type=file.content_type,
                data=data,
            )
        )
    return payloads


def build_upload_files(payloads: Iterable[FilePayload]) -> List[UploadFile]:
    uploads: List[UploadFile] = []
    for payload in payloads:
        buffer = SpooledTemporaryFile()
        buffer.write(payload.data)
        buffer.seek(0)

        headers_dict = {}
        if payload.content_type:
            headers_dict["content-type"] = payload.content_type

        headers = Headers(headers_dict) if headers_dict else None

        uploads.append(
            UploadFile(
                filename=payload.filename,
                file=buffer,
                headers=headers,
            )
        )

    return uploads


