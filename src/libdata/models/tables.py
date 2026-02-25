# libdata/models/tables.py
from email.policy import default
from operator import index
from typing import Text

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Boolean, DateTime, UniqueConstraint, Date,
      Integer, String, Boolean, ForeignKey, DateTime, Date, Text, func,Numeric,Enum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declared_attr

import uuid
from sqlalchemy.dialects.postgresql import UUID

from libdata.enums import CurrencyTypeEnum,CountryCodeEnum,PersonRoleEnum

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
    is_deleted = Column(Boolean, nullable=True, default=True)


class AuditStampMixin:
    """Timestamps only."""
    __abstract__ = True
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


class AuditByMixin:
    __abstract__ = True

    @declared_attr
    def created_by(cls):
        return Column(Integer, ForeignKey("users.id"), index=True, nullable=True)

    @declared_attr
    def updated_by(cls):
        return Column(Integer, ForeignKey("users.id"), index=True, nullable=True)

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

# class Tenant(BaseModel, AuditByMixin):  # include who created/updated a tenant
#     __tablename__ = "tenants"

#     id = Column(Integer, primary_key=True)
#     name = Column(String, unique=True, index=True, nullable=True)


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)

class User(BaseModel, AuditByMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_name = Column(String, unique=True, index=True, nullable=True)
    password = Column(String, nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)


# ---- Claims table ------------------------------------------------------

class ClaimType(BaseModel, AuditByMixin):
    __tablename__ = "claim_types"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="claim_type")


class Handler(BaseModel, AuditByMixin):
    __tablename__ = "handlers"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    claims = relationship("Claim", back_populates="handler")


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


class SourceChannel(BaseModel, AuditByMixin):
    __tablename__ = "source_channels"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    requires_staff = Column(Boolean, nullable=True, default=True)
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

class TaxiType(BaseModel, AuditByMixin):
    __tablename__ = "taxi_types"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    boroughs = relationship("Borough", back_populates="taxi_type")

class Claim(BaseModel, AuditByMixin):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)

    # Foreign Key relationships
    claim_type_id = Column(Integer, ForeignKey("claim_types.id", ondelete="SET NULL"), nullable=True, index=True)
    handler_id = Column(Integer, ForeignKey("handlers.id", ondelete="SET NULL"), nullable=True, index=True)
    target_debt_id = Column(Integer, ForeignKey("target_debts.id", ondelete="SET NULL"), nullable=True, index=True)
    case_status_id = Column(Integer, ForeignKey("case_statuses.id", ondelete="SET NULL"), nullable=True, index=True)

    source_id = Column(Integer, ForeignKey("source_channels.id", ondelete="SET NULL"), nullable=True, index=True)
    source_staff_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
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

    # Additional fields
    is_locked = Column(Boolean, nullable=True, default=False)
    client_going_abroad = Column(Boolean, nullable=True, default=False)
    abroad_date = Column(Date, nullable=True)
    manager_notified_at = Column(DateTime(timezone=True), nullable=True)

    # Tenant relationship
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    # Optional: Add relationships for easier querying
    claim_type = relationship("ClaimType", back_populates="claims")
    handler = relationship("Handler", back_populates="claims")
    target_debt = relationship("TargetDebt", back_populates="claims")
    case_status = relationship("CaseStatus", back_populates="claims")
    source = relationship("SourceChannel", back_populates="claims")
    prospect = relationship("Prospect", back_populates="claims")
    present_position = relationship("PresentFilePosition", back_populates="claims")
    location_conditions = relationship("LocationCondition", back_populates="claim", cascade="all, delete-orphan")
    police_details = relationship("PoliceDetail", back_populates="claim", cascade="all, delete-orphan")


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
    third_party_capture=Column(String(200), nullable=True, default=True)
    driver_commission_id = Column(Integer, ForeignKey("driver_commissions.id", ondelete="CASCADE"), nullable=True, index=True)
    referrer_commission_id = Column(Integer, ForeignKey("referrer_commissions.id", ondelete="CASCADE"), nullable=True, index=True)
    driver_commission = relationship("DriverCommission", backref="referrers")
    referrer_commission = relationship("ReferrerCommission", backref="referrers")

class Company(Base, AuditByMixin):
    __tablename__ = "companies"

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
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

class ReferrerCommission(Base, AuditByMixin):
    __tablename__ = "referrer_commissions"

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(Enum(CurrencyTypeEnum), default=CurrencyTypeEnum.GBP, nullable=True)
    on_hire_amount=Column(Numeric(10, 2), nullable=True)
    on_hire_paid_on=Column(Date, nullable=True)
    off_hire_amount = Column(Numeric(10, 2), nullable=True)
    off_hire_paid_on = Column(Date, nullable=True)
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
    ni_number = Column(String(50), nullable=True, unique=True)
    country = Column(
        Enum(CountryCodeEnum, name="country_code_enum"),
        default=CountryCodeEnum.UK,
        nullable=True,
    )

    # Driving details
    driver_code = Column(String(50), nullable=True)
    day_driver = Column(Boolean, nullable=True, default=True)  # True=Day, True=Night
    driver_base = Column(String(100), nullable=True)

    # Bank details
    sort_code = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True, unique=True)
    bank_details_note = Column(Text, nullable=True)

    # Flags
    ci_vat_registered = Column(Boolean, nullable=True, default=True)
    is_vulnerable = Column(Boolean, nullable=True, default=True)
    vulnerable_note = Column(Text, nullable=True)

    # Foreign Keys
    witness_independent = Column(Boolean, nullable=True, default=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    address_id = Column(Integer, ForeignKey("addresses.id", ondelete="CASCADE"), nullable=True, index=True)
    accident_detail_id = Column(Integer, ForeignKey("accident_details.id", ondelete="CASCADE"), nullable=True, index=True)


    # Contact details
    language_id = Column(Integer, ForeignKey("languages.id", ondelete="SET NULL"), nullable=True, index=True)
    speaks_clear_english = Column(Boolean, nullable=True, default=True)
    contact_via_alternative_person = Column(Boolean, nullable=True, default=True)

    alter_person = Column(String(100), nullable=True)
    alter_number = Column(String(50), nullable=True)

    # Relationships
    claim = relationship("Claim", backref="clients")
    tenant = relationship("Tenant", backref="clients")
    address = relationship("Address", backref="client_details")
    language = relationship("Language", back_populates="client_details")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    #accident_detail = relationship("AccidentDetail", backref="persons")


class Address(BaseModel, AuditByMixin):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String(255), nullable=True)
    postcode = Column(String(20), nullable=True)
    home_tel = Column(String(20), nullable=True)
    mobile_tel = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)

class LocationCondition(BaseModel, AuditByMixin):
    __tablename__ = "accident_details"

    id = Column(Integer, primary_key=True, index=True)

    # Fields
    date_time = Column(DateTime(timezone=True), nullable=True)
    condition = Column(Integer, nullable=True)
    location = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    service_date_time = Column(DateTime(timezone=True), nullable=True)
    any_passenger = Column(Boolean, default=True, nullable=True)
    passenger_no = Column(Integer, nullable=True)
    witness = Column(Boolean, default=True, nullable=True)
    police_attend = Column(Boolean, default=True, nullable=True)
    dash_footage = Column(Boolean, default=True, nullable=True)

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
        lazy="joined"
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

    fuel_type = relationship("FuelType", back_populates="client_vehicles")
    transmission = relationship("Transmission", back_populates="client_vehicles")

    # Relationships - ONE client vehicle has ONE borough and MANY third-party vehicles
    borough = relationship("Borough", back_populates="client_vehicle", uselist=True, cascade="all, delete-orphan")
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
    any_other_borough = Column(Boolean,nullable=True, default=True)
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
    images_available = Column(Boolean, nullable=True, default=True)

    client_vehicles = relationship("VehicleDetail", back_populates="third_party_vehicles")

class PoliceDetail(BaseModel, AuditByMixin):
    __tablename__ = "police_details"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200),nullable=True)
    reference_no = Column(String(200), nullable=True)
    station_name = Column(String(200), nullable=True)
    station_address = Column(String(200), nullable=True)
    incident_report_taken = Column(Boolean,nullable=True)
    report_received_date = Column(Date,nullable=True)
    additional_info = Column(Text,nullable=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)

    claim = relationship("Claim", back_populates="police_details")

class ClaimQuestionnaire(Base, AuditByMixin):
    __tablename__ = "claim_questionnaires"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    status = Column(String(50), nullable=True)
    witness_sign = Column(Text, nullable=True)    # changed from String(255)
    officer_sign = Column(Text, nullable=True)    # changed from String(255)
    witness_name = Column(String(255), nullable=True)
    officer_name = Column(String(255), nullable=True)
    date_of_witness = Column(DateTime, nullable=True)
    date_of_officer = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    # relationships
    questionnaires = relationship("Questionnaire", back_populates="claim_questionnaire", cascade="all, delete-orphan")


class Questionnaire(BaseModel, AuditByMixin):
    __tablename__ = "questionnaires"

    id = Column(Integer, primary_key=True, index=True)
    claim_questionnaire_id = Column(Integer, ForeignKey("claim_questionnaires.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    question = Column(String(500), nullable=True)
    answer = Column(String(2000), nullable=True)

    claim_questionnaire = relationship("ClaimQuestionnaire", back_populates="questionnaires")

