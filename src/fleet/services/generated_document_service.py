"""Generated Fleet document assets.

These files live inside the Fleet module so Fleet stays separable from Claims.
For now the Raise Hire Documentation source files are static Office documents
from ``fleet/assets/Documents``; this service exposes them through authenticated
Fleet routes for download/email attachment.
"""
from dataclasses import dataclass
from io import BytesIO
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fleet.services.common import get_hire_or_404


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "Documents"


@dataclass(frozen=True)
class GeneratedDocumentAsset:
    key: str
    filename: str
    source_filename: str

    @property
    def path(self) -> Path:
        return ASSET_DIR / self.source_filename

    @property
    def content_type(self) -> str:
        return mimetypes.guess_type(self.filename)[0] or "application/octet-stream"


DOCUMENT_GROUPS: Dict[str, List[GeneratedDocumentAsset]] = {
    "raise_hire_documentation": [
        GeneratedDocumentAsset(
            key="raise_hire_documentation_docx",
            filename="Raise Hire Documentation.docx",
            source_filename="Raise Hire Documentation .docx",
        ),
        GeneratedDocumentAsset(
            key="raise_hire_documentation_xls",
            filename="Raise Hire Documentation II.xls",
            source_filename="Raise Hire Documentation II.xls",
        ),
    ],
    "raise_authority_letter": [
        GeneratedDocumentAsset(
            key="raise_authority_letter_docx",
            filename="Raise Authority Letter.docx",
            source_filename="Raise Authority Letter.docx",
        ),
    ],
    "raise_vehicle_inspection_sheet": [
        GeneratedDocumentAsset(
            key="raise_vehicle_inspection_sheet_xlsx",
            filename="Vehicle Inspection Sheet.xlsx",
            source_filename="Vehicle Inspection Sheet.xlsx",
        ),
    ],
}


def _assets_for(document_key: str) -> List[GeneratedDocumentAsset]:
    assets = DOCUMENT_GROUPS.get(document_key)
    if not assets:
        raise HTTPException(status_code=404, detail="Generated document not found")
    missing = [asset.filename for asset in assets if not asset.path.exists()]
    if missing:
        raise HTTPException(status_code=404, detail=f"Document asset missing: {', '.join(missing)}")
    return assets


def list_document_files(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    document_key: str,
) -> List[dict]:
    get_hire_or_404(db, hire_id, tenant_id)
    return [
        {
            "key": asset.key,
            "filename": asset.filename,
            "content_type": asset.content_type,
            "size": asset.path.stat().st_size,
        }
        for asset in _assets_for(document_key)
    ]


def get_document_file(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    document_key: str,
    file_key: str,
) -> Tuple[bytes, str, str]:
    get_hire_or_404(db, hire_id, tenant_id)
    asset = next((item for item in _assets_for(document_key) if item.key == file_key), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Generated document file not found")
    return asset.path.read_bytes(), asset.content_type, asset.filename


def get_document_bundle(
    db: Session,
    hire_id: int,
    tenant_id: Optional[int],
    document_key: str,
) -> Tuple[bytes, str, str]:
    get_hire_or_404(db, hire_id, tenant_id)
    assets = _assets_for(document_key)
    if len(assets) == 1:
        asset = assets[0]
        return asset.path.read_bytes(), asset.content_type, asset.filename

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as zf:
        for asset in assets:
            zf.write(asset.path, arcname=asset.filename)
    return output.getvalue(), "application/zip", f"{document_key.replace('_', ' ').title()}.zip"
