# libdata/models/tables.py
from email.policy import default
from operator import index
from typing import Text

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Boolean, DateTime, UniqueConstraint, Date,
      Integer, String, Boolean, ForeignKey, DateTime, Date, Text, func,Numeric,Enum,DECIMAL
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declared_attr

from datetime import datetime
from libdata.enums import WeatherTypeEnum,CurrencyTypeEnum,CountryCodeEnum,PersonRoleEnum,DriverCheckImageType,HistoryLogType

Base = declarative_base()


# --- Mixins -------------------------------------------------------------

class TablenameMixin:
    __abstract__ = True

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()


class SoftDeleteMixin:
    __abstract__ = True
    is_active = Column(Boolean, nullable=True, default=True)
    is_deleted = Column(Boolean, nullable=True, default=False)


class AuditStampMixin:
    """Timestamps only."""
    __abstract__ = True
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


class AuditByMixin:
    __abstract__ = True

    @declared_attr
    def created_by(cls):
        # use_alter and a UNIQUE name per table are the keys here
        return Column(Integer, ForeignKey("users.id", use_alter=True, name=f"fk_{cls.__tablename__}_created_by"), index=True, nullable=True)

    @declared_attr
    def updated_by(cls):
        return Column(Integer, ForeignKey("users.id", use_alter=True, name=f"fk_{cls.__tablename__}_updated_by"), index=True, nullable=True)
    
    @declared_attr
    def created_by_user(cls):
        # Read-only helper rel; no backref to avoid cross-model clutter
        return relationship("User", foreign_keys=[cls.created_by], lazy="select")

    @declared_attr
    def updated_by_user(cls):
        return relationship("User", foreign_keys=[cls.updated_by], lazy="select")


# Base model most tables can inherit
class BaseModel(TablenameMixin, SoftDeleteMixin, AuditStampMixin, Base):
    __abstract__ = True


# --- Tables -------------------------------------------------------------

class Tenant(BaseModel, AuditByMixin):  # include who created/updated a tenant
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True, nullable=True)


class User(BaseModel, AuditByMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_name = Column(String, unique=True, index=True, nullable=True)
    password = Column(String, nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)

    # Server-side brute-force lockout (never trust the client for this).
    failed_login_attempts = Column(Integer, nullable=False, server_default="0", default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", use_alter=True, name="fk_user_tenant"), nullable=True)


# ---- Claims table ------------------------------------------------------

class ClaimType(BaseModel, AuditByMixin):
    __tablename__ = "claim_types"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="claim_type")

class CaseNote(Base):
    __tablename__ = "case_activity_notes"

    id = Column(Integer, primary_key=True, index=True)

    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)

    history_activity_id = Column(
        Integer,
        nullable=True,
        index=True,
    )

    activity_ref = Column(String(255), nullable=True, index=True)

    note = Column(Text, nullable=False)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    is_deleted = Column(Boolean, default=False)

class CaseNoteReply(Base):
    __tablename__ = "case_activity_note_replies"

    id = Column(Integer, primary_key=True, index=True)

    note_id = Column(
        Integer,
        ForeignKey("case_activity_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reply = Column(Text, nullable=False)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    is_deleted = Column(Boolean, default=False)

class Handler(BaseModel, AuditByMixin):
    __tablename__ = "handlers"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim",foreign_keys="Claim.handler_id", back_populates="handler")
    sourced_claims  = relationship("Claim",foreign_keys="Claim.source_staff_user_id", back_populates="source_staff_user")


class TargetDebt(BaseModel, AuditByMixin):
    __tablename__ = "target_debts"

    id = Column(Integer, primary_key=True)
    label = Column(String(50), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="target_debt")


class CaseStatus(BaseModel, AuditByMixin):
    __tablename__ = "case_statuses"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="case_status")

from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Boolean, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship


class CaseDocument(BaseModel, AuditByMixin):
    __tablename__ = "case_documents"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)

    file_name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=True)
    file_extension = Column(String(50), nullable=True)
    content_type = Column(String(100), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    category = Column(String(100), nullable=False, index=True)
    tag = Column(String(100), nullable=True)
    source_type = Column(String(100), nullable=True)  # claim_entrance, ai_report, witness, user_upload

    s3_key = Column(String(500), nullable=False)
    file_url = Column(String(500), nullable=True)

    version = Column(Integer, nullable=False, default=1)
    parent_document_id = Column(Integer, ForeignKey("case_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    is_latest = Column(Boolean, default=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)

    tenant_id = Column(Integer)

    metadata_json = Column(JSONB, nullable=True)

    claim = relationship("Claim", backref="case_documents")
    parent_document = relationship(
        "CaseDocument",
        foreign_keys=[parent_document_id],
        remote_side="CaseDocument.id",
        backref="child_versions",
    )


class CaseDocumentAuditLog(BaseModel, AuditByMixin):
    __tablename__ = "case_document_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_document_id = Column(Integer, ForeignKey("case_documents.id", ondelete="CASCADE"), nullable=False, index=True)

    action = Column(String(100), nullable=False)  # upload, preview, download, share, version_restore
    action_detail = Column(Text, nullable=True)

    case_document = relationship("CaseDocument", backref="audit_logs")
    
class SourceChannel(BaseModel, AuditByMixin):
    __tablename__ = "source_channels"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    requires_staff = Column(Boolean, nullable=True, default=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="source")


class Prospect(BaseModel, AuditByMixin):
    __tablename__ = "prospects"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="prospect")


class PresentFilePosition(BaseModel, AuditByMixin):
    __tablename__ = "present_file_positions"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="present_position")

class Language(BaseModel, AuditByMixin):
    __tablename__ = "languages"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    client_details = relationship("ClientDetail", back_populates="language")

class FuelType(BaseModel, AuditByMixin):
    __tablename__ = "fuel_types"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    client_vehicles = relationship("VehicleDetail", back_populates="fuel_type")

class Transmission(BaseModel, AuditByMixin):
    __tablename__ = "transmissions"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    client_vehicles = relationship("VehicleDetail", back_populates="transmission")

class VehicleStatus(BaseModel, AuditByMixin):
    __tablename__ = "vehicle_statuses"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    client_vehicles = relationship("VehicleDetail", back_populates="vehicle_status")
    third_party_vehicles = relationship("ThirdPartyVehicle", back_populates="vehicle_status")
    client_details = relationship("ClientDetail", back_populates="vehicle_status")

class TaxiType(BaseModel, AuditByMixin):
    __tablename__ = "taxi_types"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    boroughs = relationship("Borough", back_populates="taxi_type")

class SalvageCategory(BaseModel, AuditByMixin):
    __tablename__ = "salvage_categories"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

class KeepingSalvage(BaseModel, AuditByMixin):
    __tablename__ = "keeping_salvages"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

class PavAgreed(BaseModel, AuditByMixin):
    __tablename__ = "pav_agreed"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

class RetainingSalvage(BaseModel, AuditByMixin):
    __tablename__ = "retaining_salvages"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

class PolicyType(BaseModel, AuditByMixin):
    __tablename__ = "policy_types"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    insurer_brokers = relationship("InsurerBroker", back_populates="policy_type", cascade="all, delete-orphan")

class CoverLevel(BaseModel, AuditByMixin):
    __tablename__ = "cover_levels"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    insurer_brokers = relationship("InsurerBroker", back_populates="policy_cover", cascade="all, delete-orphan")

class ReasonMid(BaseModel, AuditByMixin):
    __tablename__ = "mid_reasons"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    third_party_insurers = relationship("ThirdPartyInsurer", back_populates="reason_new_mid")

class LiabilityStance(BaseModel, AuditByMixin):
    __tablename__ = "liability_stances"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    third_party_insurers = relationship("ThirdPartyInsurer", back_populates="liability_stance")

class SettlementStatus(BaseModel, AuditByMixin):
    __tablename__ = "settlement_statuses"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    third_party_insurers = relationship("ThirdPartyInsurer", back_populates="settlement_status")

class ClientVehicleCategory(BaseModel, AuditByMixin):
    __tablename__ = "client_vehicle_categories"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    hire_vehicle_provides = relationship("HireVehicleProvided", back_populates="client_vehicle_category")

class ActualVehicleCategory(BaseModel, AuditByMixin):
    __tablename__ = "actual_vehicle_categories"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    abi_rate = Column(DECIMAL, nullable=True)
    bhr_rate = Column(DECIMAL, nullable=True)
    fifty_fifty_rate = Column(DECIMAL, nullable=True)
    valet_rate = Column(DECIMAL, nullable=True, server_default="30")
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    hire_vehicle_provides = relationship("HireVehicleProvided", back_populates="actual_vehicle_category")

class AdminFeeType(BaseModel, AuditByMixin):
    __tablename__ = "admin_fee_types"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    hire_details = relationship("HireDetail", back_populates="admin_fee_type")

class HireVehicleStatus(BaseModel, AuditByMixin):
    __tablename__ = "hire_vehicle_statuses"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    hire_vehicle_provides = relationship("HireVehicleProvided", back_populates="hire_vehicle_status")

class Claim(BaseModel, AuditByMixin):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)

    # Foreign Key relationships
    claim_type_id = Column(Integer, ForeignKey("claim_types.id", ondelete="SET NULL"), nullable=True, index=True)
    handler_id = Column(Integer, ForeignKey("handlers.id", ondelete="SET NULL"), nullable=True, index=True)
    target_debt_id = Column(Integer, ForeignKey("target_debts.id", ondelete="SET NULL"), nullable=True, index=True)
    case_status_id = Column(Integer, ForeignKey("case_statuses.id", ondelete="SET NULL"), nullable=True, index=True)

    source_id = Column(Integer, ForeignKey("source_channels.id", ondelete="SET NULL"), nullable=True, index=True)
    source_staff_user_id = Column(Integer, ForeignKey("handlers.id", ondelete="SET NULL"), nullable=True, index=True)
    prospects_id = Column(Integer, ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True, index=True)
    entrant_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    present_position_id = Column(Integer, ForeignKey("present_file_positions.id", ondelete="SET NULL"), nullable=True,
                                 index=True)

    # Boolean and String fields
    credit_hire_accepted = Column(Boolean, nullable=True)
    non_fault_accident = Column(String(8), nullable=True)
    any_passengers = Column(String(8), nullable=True)
    client_injured = Column(String(8), nullable=True)

    # Date/Time fields
    file_opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    file_closed_at = Column(DateTime(timezone=True), nullable=True)
    file_closed_reason = Column(Text, nullable=True)
    # Reason captured on the General Details screen when the case status is "Rejected".
    rejection_reason = Column(Text, nullable=True)

    # Additional fields
    is_locked = Column(Boolean, nullable=True, default=False)
    client_going_abroad = Column(Boolean, nullable=True, default=False)
    abroad_date = Column(Date, nullable=True)
    manager_notified_at = Column(DateTime(timezone=True), nullable=True)
    # Per-screen "all fields filled" flags for the claim sidebar's green checks,
    # e.g. {"client": true, "accident": false}. Persisted so the sidebar can show
    # completion for every screen from a single fetch (no per-screen probing).
    screen_completion = Column(JSONB, nullable=True)

    # Tenant relationship
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    # Optional: Add relationships for easier querying
    claim_type = relationship("ClaimType", back_populates="claims")
    handler = relationship("Handler",foreign_keys=[handler_id], back_populates="claims")
    source_staff_user = relationship("Handler", foreign_keys=[source_staff_user_id], back_populates="claims")
    target_debt = relationship("TargetDebt", back_populates="claims")
    case_status = relationship("CaseStatus", back_populates="claims")
    source = relationship("SourceChannel", back_populates="claims")
    prospect = relationship("Prospect", back_populates="claims")
    present_position = relationship("PresentFilePosition", back_populates="claims")
    location_conditions = relationship("LocationCondition", back_populates="claim", cascade="all, delete-orphan")
    police_details = relationship("PoliceDetail", back_populates="claim", cascade="all, delete-orphan")
    engineer_details = relationship("EngineerDetail", back_populates="claim", cascade="all, delete-orphan")
    route_repairs = relationship("RouteRepair", back_populates="claim", cascade="all, delete-orphan")
    insurer_brokers = relationship("InsurerBroker", back_populates="claim", cascade="all, delete-orphan")
    panel_solicitors = relationship("PanelSolicitor", back_populates="claim", cascade="all, delete-orphan")
    storages = relationship("Storage", back_populates="claim", cascade="all, delete-orphan")
    recoveries = relationship("Recovery", back_populates="claim", cascade="all, delete-orphan")
    third_party_insurers = relationship("ThirdPartyInsurer", back_populates="claim", cascade="all, delete-orphan")
    hire_details = relationship("HireDetail", back_populates="claim", cascade="all, delete-orphan")
    driver_documents_agreements = relationship("DriverDocumentAgreement", back_populates="claim",cascade="all, delete-orphan")
    hire_vehicle_provides = relationship("HireVehicleProvided", back_populates="claim", cascade="all, delete-orphan")
    driver_check = relationship("DriverCheck",back_populates="claim", cascade="all,delete-orphan")

class Referrer(Base, AuditByMixin):
    __tablename__ = "referrers"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    country = Column(
        Enum(CountryCodeEnum, name="country_code_enum"),
        default=CountryCodeEnum.UK,
        nullable=True,
    )
    company_name = Column(String(200), nullable=True)
    address = Column(String(300), nullable=True)
    postcode = Column(String(20), nullable=True)
    contact_name = Column(String(100), nullable=True)
    contact_number = Column(String(50), nullable=True)
    contact_email = Column(String(150), nullable=True)
    is_active = Column(Boolean, default=True)
    solicitor=Column(String(200), nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id"),nullable=True, index=True)
    primary_contact_number = Column(String(50), nullable=True)
    third_party_capture=Column(String(200), nullable=True, default=False)
    driver_commission_id = Column(Integer, ForeignKey("driver_commissions.id", ondelete="CASCADE"), nullable=True, index=True)
    referrer_commission_id = Column(Integer, ForeignKey("referrer_commissions.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    driver_commission = relationship("DriverCommission", backref="referrers")
    referrer_commission = relationship("ReferrerCommission", backref="referrers")

class Company(Base, AuditByMixin):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(200), nullable=True)
    address = Column(String(300), nullable=True)
    postcode = Column(String(20), nullable=True)


class EngineerCompany(Base, AuditByMixin):
    """Master list of engineer/assessor companies (name + address) used for the
    Company Name autocomplete on the Engineer Details screen."""
    __tablename__ = "engineer_companies"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(200), nullable=True)
    address = Column(String(300), nullable=True)
    postcode = Column(String(20), nullable=True)


class DriverCommission(Base, AuditByMixin):
    __tablename__ = "driver_commissions"

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    on_hire_amount = Column(Numeric(10, 2), nullable=True)
    on_hire_paid_on = Column(Date, nullable=True)
    congestion_charges = Column(Numeric(10, 2), nullable=True)
    other_charges = Column(Numeric(10, 2), nullable=True)
    off_hire_amount = Column(Numeric(10, 2), nullable=True)
    off_hire_paid_on = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

class ReferrerCommission(Base, AuditByMixin):
    __tablename__ = "referrer_commissions"

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    on_hire_amount=Column(Numeric(10, 2), nullable=True)
    on_hire_paid_on=Column(Date, nullable=True)
    off_hire_amount = Column(Numeric(10, 2), nullable=True)
    off_hire_paid_on = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)


class ClientDetail(BaseModel, AuditByMixin):
    __tablename__ = "client_details"

    id = Column(Integer, primary_key=True, index=True)

    # Basic info
    role = Column(Enum(PersonRoleEnum), nullable=True, index=True)
    gender = Column(String(20), nullable=True)
    first_name = Column(String(100), nullable=True)
    surname = Column(String(100), nullable=True)
    age = Column(Integer, nullable=True)
    occupation = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    ni_number = Column(String(50), nullable=True, unique=False)
    country = Column(
        Enum(CountryCodeEnum, name="country_code_enum"),
        default=CountryCodeEnum.UK,
        nullable=True,
    )

    # Driving details
    driver_code = Column(String(50), nullable=True)
    day_driver = Column(Boolean, nullable=True, default=True)  # True=Day, False=Night
    driver_base = Column(String(100), nullable=True)

    # Bank details
    sort_code = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True, unique=False)
    bank_details_note = Column(Text, nullable=True)

    # Flags
    ci_vat_registered = Column(Boolean, nullable=True, default=False)
    is_vulnerable = Column(Boolean, nullable=True, default=False)
    vulnerable_note = Column(Text, nullable=True)

    # Foreign Keys
    witness_independent = Column(Boolean, nullable=True, default=False)
    payment_benificiary = Column(String(200),nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)
    accident_detail_id = Column(Integer, ForeignKey("accident_details.id", ondelete="CASCADE"), nullable=True, index=True)


    # Contact details
    language_id = Column(Integer, ForeignKey("languages.id", ondelete="SET NULL"), nullable=True, index=True)
    other_language = Column(String(100), nullable=True)  # free-text when language is "Other"
    speaks_clear_english = Column(Boolean, nullable=True, default=True)
    contact_via_alternative_person = Column(Boolean, nullable=True, default=False)
    vehicle_status_id = Column(Integer, ForeignKey("vehicle_statuses.id", ondelete="SET NULL"), nullable=True, index=True)

    alter_person = Column(String(100), nullable=True)
    alter_number = Column(String(50), nullable=True)

    # Dependents & caring
    dependents = Column(String(50), nullable=True)
    partner = Column(Boolean, nullable=True, default=False)
    children = Column(String(255), nullable=True)
    caring_for_elderly = Column(Boolean, nullable=True, default=False)
    dependents_details = Column(Text, nullable=True)

    # Bank details
    pay_notification_date = Column(Date, nullable=True)

    # Relationships
    claim = relationship("Claim", backref="clients")
    tenant = relationship("Tenant", backref="clients")
    address = relationship("Address", backref="client_details")
    language = relationship("Language", back_populates="client_details")
    vehicle_status = relationship("VehicleStatus", back_populates="client_details")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    #accident_detail = relationship("AccidentDetail", backref="persons")
    third_parties = relationship("ThirdPartyInsurer",foreign_keys="[ThirdPartyInsurer.third_party_id]",back_populates="third_party")
    third_party_insurers = relationship("ThirdPartyInsurer",foreign_keys="[ThirdPartyInsurer.third_party_insurer_id]",back_populates="third_party_insurer")
    third_party_handlings = relationship("ThirdPartyInsurer",foreign_keys="[ThirdPartyInsurer.third_party_handling_id]",back_populates="third_party_handling")


class Address(BaseModel, AuditByMixin):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String(255), nullable=True)
    postcode = Column(String(20), nullable=True)
    home_tel = Column(String(20), nullable=True)
    landline_tel = Column(String(20), nullable=True)
    mobile_tel = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    engineer_details = relationship("EngineerDetail", foreign_keys="[EngineerDetail.engineer_address_id]",
                                    back_populates="engineer_address", cascade="all, delete-orphan")
    vehicle_engineer_details = relationship("EngineerDetail", foreign_keys="[EngineerDetail.vehicle_address_id]",
                                            back_populates="vehicle_address")
    panel_solicitors = relationship("PanelSolicitor", back_populates="address", cascade="all, delete-orphan")
    storages = relationship("Storage", back_populates="address")
    recoveries = relationship("Recovery", back_populates="address")

class LocationCondition(BaseModel, AuditByMixin):
    __tablename__ = "accident_details"

    id = Column(Integer, primary_key=True, index=True)

    # Fields
    date_time = Column(DateTime(timezone=True), nullable=True)
    condition = Column(Integer, nullable=True)
    location = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    service_date_time = Column(DateTime(timezone=True), nullable=True)
    any_passenger = Column(Boolean, default=False, nullable=True)
    passenger_no = Column(Integer, nullable=True)
    witness = Column(Boolean, default=False, nullable=True)
    police_attend = Column(Boolean, default=False, nullable=True)
    dash_footage = Column(Boolean, default=False, nullable=True)

    # Foreign key to Claim
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationship
    claim = relationship("Claim", back_populates="location_conditions")
    passengers = relationship(
        "ClientDetail",
        primaryjoin="and_(LocationCondition.id==ClientDetail.accident_detail_id, ClientDetail.role=='PASSENGER')",
        lazy="joined"
    )

    witnesses = relationship(
        "ClientDetail",
        primaryjoin="and_(LocationCondition.id==ClientDetail.accident_detail_id, ClientDetail.role=='WITNESS')",
        lazy="joined",
        overlaps="passengers"
    )


class VehicleDetail(BaseModel,AuditByMixin):
    __tablename__ = "client_vehicles"

    id = Column(Integer,primary_key=True)
    make = Column(String(200),nullable=True)
    model = Column(String(200),nullable=True)
    body_type = Column(String(200),nullable=True)
    registration = Column(String(200),nullable=True)
    color = Column(String(200), nullable=True)
    fuel_type_id = Column(Integer, ForeignKey("fuel_types.id", ondelete="SET NULL"), nullable=True, index=True)
    engine_size = Column(String(200),nullable=True)
    transmission_id = Column(Integer, ForeignKey("transmissions.id", ondelete="SET NULL"), nullable=True, index=True)
    number_of_seat = Column(Integer,nullable=True)
    vehicle_category = Column(String(200), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    vehicle_status_id = Column(Integer, ForeignKey("vehicle_statuses.id", ondelete="SET NULL"), nullable=True, index=True)
    damage_area = Column(Text, nullable=True)
    unrelated_damage = Column(Text, nullable=True)
    damage_diagram = Column(JSONB, nullable=True)

    fuel_type = relationship("FuelType", back_populates="client_vehicles")
    transmission = relationship("Transmission", back_populates="client_vehicles")
    vehicle_status = relationship("VehicleStatus", back_populates="client_vehicles")

    # Relationships - ONE client vehicle has ONE borough and MANY third-party vehicles
    borough = relationship("Borough", back_populates="client_vehicle", uselist=False, cascade="all, delete-orphan")
    third_party_vehicles = relationship("ThirdPartyVehicle", back_populates="client_vehicles",
                                        cascade="all, delete-orphan")

class Borough(BaseModel,AuditByMixin):
    __tablename__ = "borough"

    id = Column(Integer, primary_key=True)
    client_vehicle_id = Column(Integer, ForeignKey("client_vehicles.id", ondelete="CASCADE"), nullable=True,index=True)
    borough_name = Column(String(200),nullable=True)
    taxi_type_id = Column(Integer, ForeignKey("taxi_types.id", ondelete="SET NULL"), nullable=True, index=True)
    client_badge_number = Column(String(200),nullable=True)
    badge_expiration_date = Column(Date,nullable=True)
    vehicle_badge_number = Column(String(200),nullable=True)
    any_other_borough = Column(Boolean,nullable=True, default=False)
    other_borough_name = Column(String(200), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    client_vehicle = relationship("VehicleDetail", back_populates="borough")
    taxi_type = relationship("TaxiType", back_populates="boroughs")

class ThirdPartyVehicle(BaseModel,AuditByMixin):
    __tablename__ = "third_party_vehicles"

    id = Column(Integer, primary_key=True, index=True)
    client_vehicle_id = Column(Integer, ForeignKey("client_vehicles.id", ondelete="CASCADE"), nullable=True, index=True)
    sequence = Column(Integer, nullable=True, default=1)
    make = Column(String(200),nullable=True)
    model = Column(String(200),nullable=True)
    registration = Column(String(200),nullable=True)
    color = Column(String(200), nullable=True)
    images_available = Column(Boolean, nullable=True, default=False)
    vehicle_status_id = Column(Integer, ForeignKey("vehicle_statuses.id", ondelete="SET NULL"), nullable=True, index=True)
    damage_area = Column(Text, nullable=True)
    unrelated_damage = Column(Text, nullable=True)
    damage_diagram = Column(JSONB, nullable=True)

    client_vehicles = relationship("VehicleDetail", back_populates="third_party_vehicles")
    vehicle_status = relationship("VehicleStatus", back_populates="third_party_vehicles")

class PoliceDetail(BaseModel, AuditByMixin):
    __tablename__ = "police_details"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200),nullable=True)
    reference_no = Column(String(200), nullable=True)
    station_name = Column(String(200), nullable=True)
    station_address = Column(String(200), nullable=True)
    incident_report_taken = Column(Boolean,nullable=True, default=False)
    report_received_date = Column(Date,nullable=True)
    additional_info = Column(Text,nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    claim = relationship("Claim", back_populates="police_details")

class ClaimQuestionnaire(Base, AuditByMixin):
    __tablename__ = "claim_questionnaires"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    witness_id = Column(
        Integer,
        ForeignKey("client_details.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status = Column(String(50), nullable=True)
    witness_sign = Column(Text, nullable=True)
    officer_sign = Column(Text, nullable=True)
    witness_name = Column(String(255), nullable=True)
    officer_name = Column(String(255), nullable=True)
    date_of_witness = Column(DateTime, nullable=True)
    date_of_officer = Column(DateTime, nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    questionnaires = relationship(
        "Questionnaire",
        back_populates="claim_questionnaire",
        cascade="all, delete-orphan",
    )

class Questionnaire(BaseModel, AuditByMixin):
    __tablename__ = "questionnaires"

    id = Column(Integer, primary_key=True, index=True)
    claim_questionnaire_id = Column(Integer, ForeignKey("claim_questionnaires.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    question = Column(String(500), nullable=True)
    answer = Column(String(2000), nullable=True)

    claim_questionnaire = relationship("ClaimQuestionnaire", back_populates="questionnaires")

class EngineerDetail(BaseModel,AuditByMixin):
    __tablename__ = "engineer_details"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(200),nullable=True)
    vehicle_payment_beneficiary = Column(String(200),nullable=True)
    reference = Column(String(200),nullable=True)

    #EngineerFee
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    actual_fee = Column(DECIMAL,nullable=True)
    invoice_received_on = Column(Date,nullable=True)
    invoice_paid_on = Column(Date,nullable=True)
    invoice_settled_on = Column(Date,nullable=True)
    invoice_settled_amount = Column(DECIMAL,nullable=True)

    #Engineer_Report_Instructions_Detail
    engineer_report_received = Column(Boolean,nullable=True, default=False)
    engineer_instructed = Column(Date,nullable=True)
    inspection_date = Column(Date,nullable=True)
    engineer_report_received_date = Column(Date,nullable=True)
    engineer_fee = Column(DECIMAL,nullable=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    engineer_address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)
    site = Column(String(200), nullable=True)
    vehicle_address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships
    claim = relationship("Claim", back_populates="engineer_details")
    engineer_address = relationship("Address", foreign_keys=[engineer_address_id], back_populates="engineer_details")
    vehicle_address = relationship("Address", foreign_keys=[vehicle_address_id], back_populates="vehicle_engineer_details")

class RouteRepair(BaseModel,AuditByMixin):
    __tablename__ = "route_repairs"

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    labour = Column(DECIMAL,nullable=True)
    paint_material = Column(DECIMAL,nullable=True)
    parts = Column(DECIMAL,nullable=True)
    miscellaneous = Column(DECIMAL,nullable=True)
    job_hire = Column(DECIMAL,nullable=True)
    sub_total = Column(DECIMAL,nullable=True)
    vat = Column(DECIMAL,nullable=True)
    total_inc_vat = Column(DECIMAL,nullable=True)

    cil_total_received = Column(DECIMAL,nullable=True)
    actual_repair_costs_parts = Column(DECIMAL,nullable=True)
    actual_repair_costs_labour = Column(DECIMAL,nullable=True)
    net_cil_amount = Column(DECIMAL,nullable=True)

    cil_agreed = Column(Boolean, nullable=True, default=False)
    if_roadworthy_cil_fee_agreed = Column(Boolean, nullable=True,default=False)
    agreement_received = Column(Date,nullable=True)
    eng_rep_sent_tpi = Column(Date, nullable=True)
    cil_cheque_request = Column(Date, nullable=True)
    cil_cheque_sent_cl = Column(Date, nullable=True)
    cil_removal_confirmation_received = Column(Date, nullable=True)

    repair_est_days = Column(Numeric, nullable=True)
    repair_inst = Column(Date, nullable=True)
    repair_auth = Column(Date, nullable=True)
    estimated_received = Column(Date, nullable=True)
    repair_start = Column(Date, nullable=True)
    repair_completed = Column(Date, nullable=True)

    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    claim = relationship("Claim", back_populates="route_repairs")

class TotalLoss(BaseModel,AuditByMixin):
        __tablename__ = "total_losses"

        id = Column(Integer, primary_key=True, index=True)
        claim_id = Column(Integer, ForeignKey("claims.id"), nullable=True, index=True)
        currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
        total_loss_date = Column(Date, nullable=True)
        pav = Column(DECIMAL, nullable=True)
        salvage_amount = Column(DECIMAL, nullable=True)

        salvage_category_id = Column(String(50), nullable=True)
        keeping_salvage_id = Column(String(50), nullable=True)
        pav_agreed_id = Column(String(50), nullable=True)
        retaining_salvage_id = Column(String(50), nullable=True)

        engineer_report_sent_tpi = Column(Date, nullable=True)
        pav_cheque_received = Column(Date, nullable=True)
        pav_sent_client = Column(Date, nullable=True)
        vehicle_salvage_milage = Column(Numeric, nullable=True)
        pav_offer_made_client = Column(Date, nullable=True)
        pav_offer_accepted = Column(Date, nullable=True)
        tpi_instructed_collect_saving_on = Column(Date, nullable=True)
        has_salvage_been_collected = Column(Boolean, nullable=True)
        salvage_collect_on = Column(Date, nullable=True)



class InsurerBroker(BaseModel,AuditByMixin):
    __tablename__ = "insurer_brokers"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String,nullable=True)
    address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)
    reference = Column(String, nullable=True)
    policy_number = Column(String, nullable=True)

    policy_holder = Column(String, nullable=True)
    policy_type_id = Column(Integer, ForeignKey("policy_types.id"), nullable=True, index=True)
    number_of_additional_driver = Column(Integer, nullable=True)
    number_vehicle_on_policy = Column(Integer, nullable=True)
    number_vehicle_in_use = Column(Integer, nullable=True)
    policy_cover_id = Column(Integer, ForeignKey("cover_levels.id"), nullable=True, index=True)
    policy_cover_excess = Column(DECIMAL,nullable=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    sdp = Column(Boolean, nullable=True, default=False)
    private_hire = Column(Boolean, nullable=True, default=False)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)

    policy_type = relationship("PolicyType", back_populates="insurer_brokers")
    policy_cover = relationship("CoverLevel", back_populates="insurer_brokers")
    claim = relationship("Claim", back_populates="insurer_brokers")
    address = relationship("Address", backref="insurer_brokers")

class PanelSolicitor(BaseModel, AuditByMixin):
    __tablename__ = "panel_solicitors"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(200), nullable=True)
    reference = Column(String(200), nullable=True)
    recommendation_sent = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    email_sent_date = Column(Date, nullable=True)
    accepted_sent_date = Column(Date, nullable=True)
    address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)

    address = relationship("Address", back_populates="panel_solicitors")
    claim = relationship("Claim", back_populates="panel_solicitors")

class Storage(BaseModel, AuditByMixin):
    __tablename__ = "storages"

    id = Column(Integer, primary_key=True, index=True)
    storage_provider = Column(String(200), nullable=True)
    name = Column(String(200), nullable=True)
    address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"),nullable=True, index=True)

    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    total_storage_days = Column(Integer,nullable=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    charge_per_day = Column(DECIMAL,nullable=True)
    total_storage_charges = Column(DECIMAL,nullable=True)

    claim = relationship("Claim", back_populates="storages")
    address = relationship("Address", back_populates="storages")

class Recovery(BaseModel, AuditByMixin):
    __tablename__ = "recoveries"

    id = Column(Integer, primary_key=True, index=True)
    recovery_provider = Column(String(200), nullable=True)
    name = Column(String(200), nullable=True)
    address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=True, index=True)

    date_of_recovery = Column(Date, nullable=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    recovery_charges = Column(DECIMAL,nullable=True)

    claim = relationship("Claim", back_populates="recoveries")
    address = relationship("Address", back_populates="recoveries")

class ThirdPartyInsurer(BaseModel, AuditByMixin):
    __tablename__ = "third_party_insurers"

    id = Column(Integer, primary_key=True, index=True)
    third_party_id = Column(Integer, ForeignKey("client_details.id", ondelete="CASCADE"), nullable=True, index=True)
    third_party_insurer_id = Column(Integer, ForeignKey("client_details.id", ondelete="CASCADE"), nullable=True,index=True)
    third_party_handling_id = Column(Integer, ForeignKey("client_details.id", ondelete="CASCADE"), nullable=True,index=True)
    direct_email = Column(String(100), nullable=True)
    insurer_reference = Column(String(200),nullable=True)
    policy_number = Column(String(200), nullable=True)
    claim_validation = Column(Boolean, nullable=True, default=False)
    handling_reference = Column(String(200), nullable=True)
    incorrect_mid_reference = Column(String(15), nullable=True)
    handler_id = Column(Integer, ForeignKey("handlers.id", ondelete="SET NULL"), nullable=True, index=True)
    incorrect_acc = Column(Date, nullable=True)
    initial_eng_made = Column(Date, nullable=True)
    new_mid = Column(String(15), nullable=True)
    new_mid_search_ref = Column(Text, nullable=True)
    incorrect_reg = Column(String(200), nullable=True)
    new_mid_search_processed = Column(Boolean, nullable=True, default=False)
    abi_insured = Column(Boolean, nullable=True, default=False)
    liability_accepted_on = Column(String(200), nullable=True)

    reason_new_mid_id = Column(Integer, ForeignKey("mid_reasons.id", ondelete="SET NULL"), nullable=True, index=True)
    liability_stance_id = Column(Integer, ForeignKey("liability_stances.id", ondelete="SET NULL"), nullable=True,index=True)
    settlement_status_id = Column(Integer, ForeignKey("settlement_statuses.id", ondelete="SET NULL"), nullable=True,index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships for easier ORM querying
    claim = relationship("Claim", back_populates="third_party_insurers")
    third_party = relationship("ClientDetail", foreign_keys=[third_party_id], back_populates="third_parties")
    third_party_insurer = relationship("ClientDetail", foreign_keys=[third_party_insurer_id],back_populates="third_party_insurers")
    third_party_handling = relationship("ClientDetail", foreign_keys=[third_party_handling_id],back_populates="third_party_handlings")
    reason_new_mid = relationship("ReasonMid", back_populates="third_party_insurers")
    liability_stance = relationship("LiabilityStance", back_populates="third_party_insurers")
    settlement_status = relationship("SettlementStatus", back_populates="third_party_insurers")

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Boolean, DateTime, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

class VehicleDamageAIReport(BaseModel, AuditByMixin):
    __tablename__ = "vehicle_damage_ai_reports"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    client_vehicle_id = Column(Integer, ForeignKey("client_vehicles.id", ondelete="CASCADE"), nullable=True, index=True)
    third_party_vehicle_id = Column(Integer, ForeignKey("third_party_vehicles.id", ondelete="CASCADE"), nullable=True, index=True)

    damage_side = Column(String(200), nullable=True)
    area_of_damage = Column(String(500), nullable=True)
    type_of_damage = Column(String(500), nullable=True)
    severity = Column(String(100), nullable=True)
    confidence_percent = Column(Integer, nullable=True)
    total_damaged_points_identified = Column(Integer, nullable=True)
    suggested_repair_action = Column(String(500), nullable=True)
    vehicle_status_id = Column(Integer, ForeignKey("vehicle_statuses.id", ondelete="SET NULL"), nullable=True, index=True)

    raw_result = Column(JSONB, nullable=True)

    # NEW
    report_payload = Column(JSONB, nullable=True)
    pdf_report_url = Column(String(500), nullable=True)

    version = Column(Integer, nullable=True, default=1, index=True)
    parent_report_id = Column(Integer, ForeignKey("vehicle_damage_ai_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    is_latest = Column(Boolean, nullable=True, default=True, index=True)
    version_notes = Column(Text, nullable=True)
    superseded_at = Column(DateTime, nullable=True)
    superseded_by_id = Column(Integer, ForeignKey("vehicle_damage_ai_reports.id", ondelete="SET NULL"), nullable=True)

    client_vehicle = relationship("VehicleDetail", backref="ai_reports")
    third_party_vehicle = relationship("ThirdPartyVehicle", backref="ai_reports")
    vehicle_status = relationship("VehicleStatus")

    parent_report = relationship(
        "VehicleDamageAIReport",
        foreign_keys=[parent_report_id],
        remote_side="VehicleDamageAIReport.id",
        backref="child_versions",
    )
    superseded_by = relationship(
        "VehicleDamageAIReport",
        foreign_keys=[superseded_by_id],
        remote_side="VehicleDamageAIReport.id",
    )


class VehicleDamageAIImage(BaseModel, AuditByMixin):
    __tablename__ = "vehicle_damage_ai_images"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("vehicle_damage_ai_reports.id", ondelete="CASCADE"), nullable=True, index=True)
    file_path = Column(String(500), nullable=True)
    original_filename = Column(String(255), nullable=True)

    report = relationship("VehicleDamageAIReport", backref="images")
    
class HireDetail(BaseModel,AuditByMixin):
    __tablename__ = "hire_details"

    id = Column(Integer, primary_key=True, index=True)
    hire_vehicle_provided_id = Column(Integer,ForeignKey("hire_vehicle_provides.id", ondelete="CASCADE"),nullable=True,index=True)
    hire_out = Column(DateTime, nullable=True)
    hire_back = Column(DateTime, nullable=True)
    no_of_days_hire_so_far = Column(Numeric, nullable=True)
    final_total_no_of_hire_days = Column(Numeric, nullable=True)
    vehicle_file_reference = Column(Text, nullable=True)
    registration_number = Column(String(100), nullable=True)
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    abi_insurer = Column(Boolean, nullable=True, default=False)
    abi_hire_charge_per_day = Column(DECIMAL,nullable=True)
    abi_extra_charges_per_day = Column(DECIMAL,nullable=True)
    admin_fee_id = Column(Integer, ForeignKey("admin_fee_types.id", ondelete="CASCADE"), nullable=True, index=True)
    abi_administration_fee = Column(DECIMAL,nullable=True)
    total_abi_hire_charge = Column(DECIMAL,nullable=True)
    bhr_hire_charge_per_day = Column(DECIMAL,nullable=True)
    bhr_extra_charges_per_day = Column(DECIMAL,nullable=True)
    bhr_administration_fee = Column(DECIMAL,nullable=True)
    cdw_charges = Column(DECIMAL,nullable=True)
    collection_delivery_fee = Column(DECIMAL,nullable=True)
    total_bhr_charges = Column(DECIMAL,nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    claim = relationship("Claim", back_populates="hire_details")
    admin_fee_type = relationship("AdminFeeType",back_populates="hire_details")
    hire_vehicle_provided = relationship("HireVehicleProvided", back_populates="hire_details")


class DriverDocumentAgreement(BaseModel, AuditByMixin):
    __tablename__ = "driver_documents_agreements"

    id = Column(Integer, primary_key=True, index=True)

    # Section 1: Driver Proofs Check List
    driver_license_received_on = Column(DateTime, nullable=True)
    driver_license_file_url = Column(String, nullable=True)

    license_checks_completed_on = Column(DateTime, nullable=True)
    license_checks_completed_file_url = Column(String, nullable=True)

    proof_of_address_1_received_on = Column(DateTime, nullable=True)
    proof_of_address_1_file_url = Column(String, nullable=True)

    proof_of_address_2_received_on = Column(DateTime, nullable=True)
    proof_of_address_2_file_url = Column(String, nullable=True)

    pre_hire_bank_statement_received_on = Column(DateTime, nullable=True)
    pre_hire_bank_statement_file_url = Column(String, nullable=True)

    post_hire_bank_statement_received_on = Column(DateTime, nullable=True)
    post_hire_bank_statement_file_url = Column(String, nullable=True)

    taxi_badge_received_on = Column(DateTime, nullable=True)
    taxi_badge_file_url = Column(String, nullable=True)

    v5_received_on = Column(DateTime, nullable=True)
    v5_file_url = Column(String, nullable=True)

    mot_certificate_received_on = Column(DateTime, nullable=True)
    mot_certificate_file_url = Column(String, nullable=True)

    insurance_certificate_received_on = Column(DateTime, nullable=True)
    insurance_certificate_file_url = Column(String, nullable=True)

    suspension_notice_received_on = Column(DateTime, nullable=True)
    suspension_notice_file_url = Column(String, nullable=True)

    suspension_uplift_received_on = Column(DateTime, nullable=True)
    suspension_uplift_file_url = Column(String, nullable=True)

    # Section 2: Agreements & Statements
    signed_cha_received_on = Column(DateTime, nullable=True)
    signed_cha_file_url = Column(String, nullable=True)

    signed_mitigation_received_on = Column(DateTime, nullable=True)
    signed_mitigation_file_url = Column(String, nullable=True)

    arf_received_on = Column(DateTime, nullable=True)
    arf_file_url = Column(String, nullable=True)

    signed_cil_agreement_received_on = Column(DateTime, nullable=True)
    signed_cil_agreement_file_url = Column(String, nullable=True)

    claim_id = Column(
        Integer,
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    claim = relationship("Claim", back_populates="driver_documents_agreements")


class HireVehicleProvided(BaseModel, AuditByMixin):
    __tablename__ = "hire_vehicle_provides"

    id = Column(Integer, primary_key=True, index=True)
#Section A - Credit Hire Documentation & Instructions
    inst_fleet_on_hire = Column(DateTime, nullable=True)
    inst_fleet_off_hire = Column(DateTime, nullable=True)
    hire_vehicle_check_sheet = Column(DateTime, nullable=True)
    recovery_storage = Column(DateTime, nullable=True)
    mitigation_questionnaire  = Column(DateTime, nullable=True)
    hire_documentation = Column(DateTime, nullable=True)
    fee_exemption_form = Column(DateTime, nullable=True)
    send_licensing_document_account = Column(DateTime, nullable=True)
    request_updated_insurance_schedule = Column(DateTime, nullable=True)
    raise_authority_letter = Column(DateTime, nullable=True)

#Section B — Hire Vehicle Provision
    client_vehicle_category_id = Column(Integer, ForeignKey("client_vehicle_categories.id", ondelete="CASCADE"),nullable=True, index=True)
    actual_vehicle_category_id = Column(Integer, ForeignKey("actual_vehicle_categories.id", ondelete="CASCADE"), nullable=True, index=True)
    cross_hire = Column(Boolean, nullable=True, default=False)
    hire_vehicle_status_id = Column(Integer, ForeignKey("hire_vehicle_statuses.id", ondelete="SET NULL"),nullable=True)
    provider_name = Column(String(200), nullable=True)
    contact_number = Column(String(50), nullable=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    rate = Column(DECIMAL, nullable=True)
    hire_vehicle_registration = Column(String(200), nullable=True)
    make = Column(String(200), nullable=True)
    model = Column(String(200), nullable=True)
    hire_start_date =  Column(Date, nullable=True)
    hire_end_date =  Column(Date, nullable=True)
    fuel_type = Column(String(200), nullable=True)
    plate_transfer = Column(Boolean, nullable=True, default=False)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships
    claim = relationship("Claim", back_populates="hire_vehicle_provides")
    client_vehicle_category = relationship("ClientVehicleCategory", back_populates="hire_vehicle_provides")
    actual_vehicle_category = relationship("ActualVehicleCategory", back_populates="hire_vehicle_provides")
    hire_vehicle_status = relationship("HireVehicleStatus", back_populates="hire_vehicle_provides")
    driver_checks = relationship("DriverCheck", back_populates="hire_vehicle_provided")
    hire_details = relationship("HireDetail", back_populates="hire_vehicle_provided")

class DriverCheck(BaseModel, AuditByMixin):
    __tablename__ = "in_out_drivers"

    id = Column(Integer, primary_key=True, index=True)
    hire_vehicle_provided_id = Column(Integer,ForeignKey("hire_vehicle_provides.id", ondelete="CASCADE"),nullable=True,index=True)
#Pop up fields
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    interior_clean_at_check_out = Column(Boolean, nullable=True, default=True)
    interior_clean_at_check_in  = Column(Boolean, nullable=True, default=True)
    interior_damage_at_check_in = Column(Boolean, nullable=True, default=False)
    describe_interior_damage = Column(Text, nullable=True)
    exterior_clean_at_check_out = Column(Boolean, nullable=True, default=True)
    exterior_clean_at_check_in = Column(Boolean, nullable=True, default=True)
    exterior_damage_at_check_in = Column(Boolean, nullable=True, default=False)
    describe_exterior_damage = Column(Text, nullable=True)
    apply_petrol_checkout_charges = Column(Boolean, nullable=True, default=False)
    petrol_checkout_charges = Column(DECIMAL, nullable=True)
    petrol_charges_note = Column(String(250), nullable=True)
    apply_damage_charges = Column(Boolean, nullable=True, default=False)
    damage_charges = Column(DECIMAL, nullable=True)
    damage_charges_paid_now = Column(DECIMAL, nullable=True)
    damage_charges_note = Column(String(250), nullable=True)
    valet_charges = Column(DECIMAL, nullable=True)
# DriverCheck charges Fields
    damage_charges_paid = Column(Boolean, nullable=True, default=False)
    total_driver_checkout_charges = Column(DECIMAL, nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    # Relationships
    claim = relationship("Claim", back_populates="driver_check")
    hire_vehicle_provided = relationship("HireVehicleProvided", back_populates="driver_checks")
    images = relationship("DriverCheckImage", back_populates="driver_check", cascade="all, delete-orphan")

class DriverCheckImage(BaseModel, AuditByMixin):
    __tablename__ = "driver_check_images"

    id = Column(Integer, primary_key=True, index=True)
    driver_check_id = Column(Integer, ForeignKey("in_out_drivers.id", ondelete="CASCADE"), nullable=True, index=True)
    image_type = Column(Enum(DriverCheckImageType), nullable=True)
    file_path = Column(String(1024), nullable=True)
    original_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    driver_check = relationship("DriverCheck", back_populates="images")

class HistoryActivities(BaseModel, AuditByMixin):
    __tablename__ = "history_activities"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255),nullable=True)
    file_path = Column(String(1024),nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    file_type = Column(Enum(HistoryLogType),nullable=True)


class PlatingAdditionalCharges(BaseModel, AuditByMixin):
    __tablename__ = "plating_additional_charges"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    # Plating is per HIRE (provided) vehicle — holds a hire_vehicle_provides id
    # (no FK; nullable for legacy/single-vehicle per-claim rows).
    client_vehicle_id = Column(Integer, nullable=True, index=True)
    private_hire_plating_fee = Column(Numeric(10, 2), nullable=True)
    private_hire_mot_cost = Column(Numeric(10, 2), nullable=True)
    total_plating_cost = Column(Numeric(10, 2), nullable=True)
    automatic = Column(Numeric(10, 2), nullable=True)
    estate = Column(Numeric(10, 2), nullable=True)
    additional_premium = Column(Numeric(10, 2), nullable=True)
    additional_driver_charges = Column(Numeric(10, 2), nullable=True)


class ABIBHRCharges(BaseModel, AuditByMixin):
    __tablename__ = "abi_bhr_charges"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_pack_raised_date = Column(Date, nullable=True)
    payment_pack_sent_date = Column(Date, nullable=True)
    invoice_number = Column(String(100), nullable=True)
    date_hire_paid = Column(Date, nullable=True)


class ComparisonSettlement(BaseModel, AuditByMixin):
    __tablename__ = "comparison_settlements"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    # Holds a hire_vehicle_provides id (NOT a client_vehicle). NULL = claim-level
    # row used when the claim has a single hire vehicle. When the claim has 2+
    # hire vehicles, the agreed HIRE values (days/rate) are stored per vehicle so
    # each card keeps its own figures; storage/recovery/engineer/plating/repair
    # stay claim-level and are counted once in the totals.
    hire_vehicle_id = Column(Integer, nullable=True, index=True)
    settlement_status = Column(String(200), nullable=True)
    abi_rate_band = Column(String(10), nullable=True)  # "10", "15", "20", "35"
    agreed_hire_days = Column(Numeric(10, 2), nullable=True)
    agreed_hire_rate = Column(Numeric(10, 4), nullable=True)
    agreed_storage_days = Column(Numeric(10, 2), nullable=True)
    agreed_storage_rate = Column(Numeric(10, 4), nullable=True)
    agreed_cdw_days = Column(Numeric(10, 2), nullable=True)
    agreed_cdw_rate = Column(Numeric(10, 4), nullable=True)
    agreed_additional_fees = Column(Numeric(10, 2), nullable=True)
    agreed_penalties = Column(Numeric(10, 2), nullable=True)
    agreed_repair_rate = Column(Numeric(10, 2), nullable=True)
    agreed_recovery_rate = Column(Numeric(10, 2), nullable=True)
    agreed_engineer_rate = Column(Numeric(10, 2), nullable=True)
    agreed_plating_rate = Column(Numeric(10, 2), nullable=True)
    agreed_cd_fee = Column(Numeric(10, 2), nullable=True)
    agreed_admin = Column(Numeric(10, 2), nullable=True)
    vat_recovered = Column(Boolean, nullable=True)
    reason_for_reduction = Column(Text, nullable=True)


class HirePaymentDetails(BaseModel, AuditByMixin):
    __tablename__ = "hire_payment_details"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_amount = Column(Numeric(10, 2), nullable=True)
    received_date = Column(Date, nullable=True)
    payment_reason = Column(Text, nullable=True)
    payments_received_total = Column(Numeric(10, 2), nullable=True)
    write_off_amount = Column(Numeric(10, 2), nullable=True)
    payment_outstanding_incl_vat = Column(Numeric(10, 2), nullable=True)
    payment_outstanding_excl_vat = Column(Numeric(10, 2), nullable=True)


class DirectHirePayment(BaseModel, AuditByMixin):
    __tablename__ = "direct_hire_payments"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    date_settlement_received = Column(Date, nullable=True)
    settlement_amount_received = Column(Numeric(10, 2), nullable=True)


class UserSession(BaseModel):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)
    device_info = Column(String(500), nullable=True)
    is_current = Column(Boolean, nullable=True, default=False)


class PasswordHistory(Base):
    __tablename__ = "password_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    password_hash = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class Task(BaseModel, AuditByMixin):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    assigned_user = Column(String(150), nullable=True)              # sample users for now (free text)
    department = Column(String(100), nullable=True)                 # Claims / Fleet / Recovery / Customer Service
    due_date = Column(Date, nullable=True)
    due_time = Column(String(20), nullable=True)                    # "16:00"
    priority = Column(String(20), nullable=True, default="Medium")  # Low / Medium / High
    status = Column(String(40), nullable=True, default="Pending")   # Pending / In Progress / Overdue / Awaiting Response / Rejected / Completed
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True)
    claim_reference = Column(String(100), nullable=True)            # denormalised display ref
    vehicle_registration = Column(String(100), nullable=True)
    attachment_path = Column(String(1024), nullable=True)
    notes = Column(Text, nullable=True)                             # "Add Note" quick action
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)


class Notification(BaseModel):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    actor_user_id = Column(Integer, nullable=True)                  # who triggered it
    tenant_id = Column(Integer, nullable=True, index=True)
    category = Column(String(50), nullable=True)                    # Mention / Task / Claim / Fleet / Recovery / System
    tab = Column(String(30), nullable=True)                         # Mentions / Tasks / Claims / Fleet / Recovery / System
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    claim_id = Column(Integer, nullable=True)                       # linked record (for click-through)
    is_read = Column(Boolean, nullable=True, default=False)


class TaskNote(BaseModel):
    __tablename__ = "task_notes"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id = Column(Integer, nullable=True)
    text = Column(Text, nullable=True)
    tenant_id = Column(Integer, nullable=True, index=True)


class TaskHistory(BaseModel):
    __tablename__ = "task_history"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(Integer, nullable=True)
    event_type = Column(String(50), nullable=True)   # created / assigned / status / attachment / note
    title = Column(String(255), nullable=True)
    detail = Column(Text, nullable=True)
    tenant_id = Column(Integer, nullable=True, index=True)


class CalendarEvent(BaseModel, AuditByMixin):
    """Calendar / scheduling events (Calendar module). Distinct from Tasks: an
    event may *link* to a task/claim/vehicle. `source` distinguishes manually
    created events from system-generated ones (Phase 3)."""
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    title = Column(String(300), nullable=False)
    event_type = Column(String(50), nullable=True)
    # Scheduled (default) / Completed / Cancelled
    status = Column(String(20), nullable=True, default="Scheduled")

    start_date = Column(Date, nullable=True, index=True)
    start_time = Column(String(5), nullable=True)   # "HH:MM"
    end_date = Column(Date, nullable=True)
    end_time = Column(String(5), nullable=True)

    assigned_users = Column(Text, nullable=True)    # comma-separated display names
    department = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    location = Column(String(300), nullable=True)

    reminder = Column(String(20), nullable=True)        # 15m / 30m / 1h / 1d
    reminder_sent = Column(Boolean, nullable=True, default=False)
    recurrence_rule = Column(String(20), nullable=True)  # Daily / Weekly / Monthly / Yearly
    # Per-occurrence overrides for a recurring series, JSON keyed by occurrence date
    # (ISO): {"2026-06-23": "Cancelled" | "Completed" | "Deleted"}. Lets a single
    # occurrence be cancelled/completed/deleted without touching the rest.
    recurrence_overrides = Column(Text, nullable=True)
    attachment_path = Column(Text, nullable=True)
    attachment_name = Column(String(300), nullable=True)

    # Linked CRM records
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True)
    claim_reference = Column(String(100), nullable=True)
    case_reference = Column(String(100), nullable=True)
    task_id = Column(Integer, nullable=True, index=True)
    vehicle_registration = Column(String(50), nullable=True)

    # System-generated event tracking (Phase 3). Manual events use source="manual".
    source = Column(String(20), nullable=True, default="manual")  # manual / system
    source_type = Column(String(50), nullable=True)   # e.g. task_due, vehicle_collection
    source_ref_id = Column(Integer, nullable=True, index=True)


class CalendarEventAudit(BaseModel):
    """Audit trail for calendar events (created / updated / completed / cancelled
    / deleted)."""
    __tablename__ = "calendar_event_audit"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, index=True, nullable=True)
    action = Column(String(30), nullable=True)
    detail = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True)
    tenant_id = Column(Integer, nullable=True, index=True)