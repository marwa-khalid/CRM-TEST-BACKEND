"""The ONLY seam between the Fleet slice and the host (Claims) app.

Every external dependency Fleet needs — the DB Base/session, auth, object
storage, and the tenant/actor helpers — is imported here and nowhere else in
``src/fleet``. To lift Fleet into its own project you rewrite just this file
(point it at Fleet's own Base/session/auth/storage) and the rest of the package
moves unchanged.
"""
from libdata.models.tables import (
    Base,
    AuditStampMixin,
    AuditByMixin,
    SoftDeleteMixin,
)
from libdata.settings import get_session
from libauth.auth import authenticate
from appflow.utils import get_tenant_id, actor_id, handler_name_for_user
from appflow.services.s3_service import S3Service
from appflow.services.email_delivery import send_email

__all__ = [
    "Base",
    "AuditStampMixin",
    "AuditByMixin",
    "SoftDeleteMixin",
    "get_session",
    "authenticate",
    "get_tenant_id",
    "actor_id",
    "handler_name_for_user",
    "S3Service",
    "send_email",
]
