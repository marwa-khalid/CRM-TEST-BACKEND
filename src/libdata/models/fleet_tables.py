"""Fleet module tables — kept in a separate file (and prefixed `fleet_`) so the
Fleet domain stays independent of Claims and can be extracted later. Shares the
same declarative Base/metadata as the rest of libdata so one Alembic migration
and cross-table FKs work.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Date, Text
from sqlalchemy.sql import func

from libdata.models.tables import Base, AuditStampMixin, AuditByMixin, SoftDeleteMixin


class FleetHire(Base, AuditStampMixin, AuditByMixin, SoftDeleteMixin):
    """One hire file. Holds General Details, Driver Details and GDPR sections as
    columns so the client can field-level PATCH them (like the Claims side)."""
    __tablename__ = "fleet_hire"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, index=True, nullable=True)

    # --- General Details ---
    file_opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    file_closed_at = Column(DateTime(timezone=True), nullable=True)
    insurance_type = Column(String(100), nullable=True)
    rental_advisor = Column(String(200), nullable=True)
    current_position = Column(String(100), nullable=True)
    bank_name = Column(String(200), nullable=True)
    account_name = Column(String(200), nullable=True)
    sort_code = Column(String(20), nullable=True)
    account_number = Column(String(50), nullable=True)

    # --- Driver Details ---
    driver_name = Column(String(200), nullable=True)
    driver_address = Column(Text, nullable=True)
    driver_postcode = Column(String(20), nullable=True)
    driver_email = Column(String(200), nullable=True)
    driver_telephone = Column(String(50), nullable=True)
    driver_mobile = Column(String(50), nullable=True)
    driving_licence_number = Column(String(100), nullable=True)
    national_insurance_number = Column(String(50), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    driving_licence_start = Column(Date, nullable=True)
    driving_licence_end = Column(Date, nullable=True)

    # --- GDPR & Marketing Preferences ---
    where_found = Column(String(100), nullable=True)
    privacy_notice_explained = Column(String(10), nullable=True)  # yes | no
    privacy_notice_date = Column(Date, nullable=True)
    privacy_notice_method = Column(String(50), nullable=True)
    lawful_basis = Column(String(50), nullable=True)
    email_consent = Column(String(20), nullable=True)  # yes | no | withdrawn
    email_consent_date = Column(Date, nullable=True)
    email_consent_method = Column(String(50), nullable=True)
    sms_consent = Column(String(20), nullable=True)
    phone_consent = Column(String(20), nullable=True)
    postal_consent = Column(String(20), nullable=True)
    reason_for_withdrawal = Column(Text, nullable=True)


class FleetHireDocument(Base, AuditStampMixin):
    """A document attached to a hire (utility bills, licence front/back, etc.)."""
    __tablename__ = "fleet_hire_document"

    id = Column(Integer, primary_key=True, index=True)
    hire_id = Column(Integer, ForeignKey("fleet_hire.id", ondelete="CASCADE"), index=True, nullable=False)
    doc_type = Column(String(50), nullable=False)  # first_utility, second_utility, dl_front, dl_back, driving_licence
    filename = Column(String(300), nullable=True)
    s3_key = Column(String(500), nullable=True)
    file_url = Column(Text, nullable=True)
    storage_backend = Column(String(50), nullable=True)
    received_on = Column(Date, nullable=True)
    extracted_address = Column(Text, nullable=True)
    created_by = Column(Integer, nullable=True)
