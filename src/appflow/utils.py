from typing import Optional
from fastapi import Request
from libdata.settings import settings
from libdata.models.tables import ClientDetail,Claim
from libdata.enums import PersonRoleEnum

def get_tenant_id(request:Request):
    return request.state.tenant_id

def actor_id(request: Request) -> Optional[int]:
    try:
        return request.state.user_id
    except Exception:
        return None

def get_full_url(file_path: str) -> str:
    """
    Convert a relative file path to a full URL using the BASE_URL from settings.
    
    Args:
        file_path: Relative file path (e.g., "/uploads/ai/123/456/image.jpg" or "uploads/ai/123/456/image.jpg")
    
    Returns:
        Full URL (e.g., "https://ed8250a730d2.ngrok.app/uploads/ai/123/456/image.jpg")
    """
    if not file_path:
        return ""
    
    # Handle blob URLs or already absolute URLs
    if file_path.startswith(("http://", "https://", "blob:")):
        return file_path
    
    # Ensure the file_path starts with /
    if not file_path.startswith("/"):
        file_path = "/" + file_path
    
    # Combine base URL with file path
    base_url = settings.base_url.rstrip("/")
    return f"{base_url}{file_path}"

def build_case_reference(claim,db) -> str:
    claim = db.query(Claim).filter(Claim.id == claim).first()
    if not claim:
        return str(claim)
    year = claim.file_opened_at.strftime("%Y")
    month = claim.file_opened_at.strftime("%m")
    padded_id = str(claim.id).zfill(5)
    client = (
        db.query(ClientDetail)
        .filter(
            ClientDetail.claim_id == claim.id,
            ClientDetail.role == PersonRoleEnum.CLIENT
        )
        .first()
    )

    if client and client.surname:
        return f"{client.surname}-{year}{month}-{padded_id}"
    return f"{year}{month}-{padded_id}"


def handler_name_for_claim(claim, db=None) -> str:
    """The claim handler is the user who created/owns the claim, displayed as
    their username (the email before '@'). Falls back to the legacy Handler
    lookup label, then an empty string. ``claim`` may be a Claim object or an id.
    """
    if claim is None:
        return ""
    from libdata.models.tables import User
    if not hasattr(claim, "created_by") and db is not None:
        claim = db.query(Claim).filter(Claim.id == claim).first()
        if claim is None:
            return ""
    user = getattr(claim, "created_by_user", None)
    if user is None and db is not None and getattr(claim, "created_by", None):
        user = db.query(User).filter(User.id == claim.created_by).first()
    if user is not None:
        un = (getattr(user, "user_name", "") or "").strip()
        if un:
            return un.split("@")[0] if "@" in un else un
    h = getattr(claim, "handler", None)
    return (getattr(h, "label", "") or "") if h else ""


def handler_name_for_user(db, user_id) -> str:
    """Display name (email before '@') for a specific user — used as the claim
    handler on outgoing letters/emails, i.e. the logged-in user who is sending."""
    if not user_id or db is None:
        return ""
    from libdata.models.tables import User
    u = db.query(User).filter(User.id == user_id).first()
    un = (getattr(u, "user_name", "") or "").strip() if u else ""
    if not un:
        return ""
    return un.split("@")[0] if "@" in un else un


def build_invoice_reference(claim_id: int) -> str:
    """Auto invoice reference for a claim, e.g. INV-202606-0022.
    Uses the current (generation) month — it's stored once so it stays stable."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return f"INV-{now.strftime('%Y%m')}-{str(claim_id).zfill(4)}"