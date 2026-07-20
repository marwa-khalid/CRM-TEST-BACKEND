"""Fleet module tables — kept in a separate file (and prefixed `fleet_`) so the
Fleet domain stays independent of Claims and can be extracted later. Shares the
same declarative Base/metadata as the rest of libdata so one Alembic migration
and cross-table FKs work.
"""
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Date, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from fleet.deps import Base, AuditStampMixin, AuditByMixin, SoftDeleteMixin


class FleetHire(Base, AuditStampMixin, AuditByMixin, SoftDeleteMixin):
    """One hire file. Holds General Details, Driver Details and GDPR sections as
    columns so the client can field-level PATCH them (like the Claims side)."""
    __tablename__ = "fleet_hire"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, index=True, nullable=True)
    fleet_reference = Column(String(50), unique=True, index=True, nullable=True)

    # --- General Details ---
    file_opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    file_closed_at = Column(DateTime(timezone=True), nullable=True)
    insurance_type = Column(String(100), nullable=True)
    rental_advisor = Column(String(200), nullable=True)
    current_position = Column(String(100), nullable=True)
    # taxi_driver | non_taxi_driver — "taxi_driver" unlocks the Taxi Badge step.
    hirer_type = Column(String(50), nullable=True)
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

    # --- Taxi Badge (only when hirer_type = taxi_driver) ---
    taxi_badge_number = Column(String(100), nullable=True)
    taxi_badge_name = Column(String(200), nullable=True)
    taxi_badge_expiry = Column(Date, nullable=True)
    taxi_badge_council = Column(String(200), nullable=True)
    taxi_badge_type = Column(String(100), nullable=True)
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

    # --- Hire Vehicle Details (screen 5) ---
    vehicle_cost_per_week = Column(String(50), nullable=True)
    deposit = Column(String(50), nullable=True)
    borough = Column(String(100), nullable=True)
    registration_number = Column(String(50), nullable=True)
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    transmission = Column(String(50), nullable=True)
    hire_status = Column(String(20), nullable=True)  # on_hire | off_hire
    swap_car = Column(String(10), nullable=True)  # yes | no
    swap_reason = Column(String(100), nullable=True)
    swap_reason_text = Column(Text, nullable=True)
    hire_start_date = Column(Date, nullable=True)
    hire_end_date = Column(Date, nullable=True)
    total_hire_period = Column(String(100), nullable=True)
    hire_insurance_type = Column(String(100), nullable=True)
    insurance_date_received = Column(Date, nullable=True)
    policy_start_date = Column(Date, nullable=True)
    policy_end_date = Column(Date, nullable=True)
    # Swap → "If Vehicle Cross-Hired to Us" modal
    cross_hire_provider_name = Column(String(200), nullable=True)
    cross_hire_contact_details = Column(String(200), nullable=True)
    cross_hire_rate = Column(String(50), nullable=True)

    # --- Payment Details (screen 7) ---
    payment_hire_start_date = Column(Date, nullable=True)
    payment_hire_end_date = Column(Date, nullable=True)
    vehicle_cost_per_day = Column(String(50), nullable=True)
    number_of_weekly_payments = Column(String(20), nullable=True)
    payment_day = Column(String(50), nullable=True)
    security_deposit = Column(String(50), nullable=True)
    weekly_hire_payment = Column(String(50), nullable=True)
    total_planned_hire_cost = Column(String(50), nullable=True)
    initial_amount_due = Column(String(50), nullable=True)
    payment_damage_charges = Column(String(50), nullable=True)
    additional_charges = Column(String(100), nullable=True)
    # The payment day a reminder was last sent FOR (not when it was sent), so the
    # daily job stays idempotent even if it runs several times a day.
    payment_reminder_sent_for = Column(Date, nullable=True)


class FleetHirePayment(Base, AuditStampMixin):
    """One row of a hire's weekly payment schedule (Record Payment).

    `paid_amount` is the running total for the week — the sum of its individual
    transactions (split / part payments). `payment_date`/`payment_time` mirror the
    most recent transaction so the schedule table can show a single summary line."""
    __tablename__ = "fleet_hire_payment"

    id = Column(Integer, primary_key=True, index=True)
    hire_id = Column(Integer, ForeignKey("fleet_hire.id", ondelete="CASCADE"), index=True, nullable=False)
    vehicle_id = Column(Integer, ForeignKey("fleet_hire_vehicle.id", ondelete="CASCADE"), index=True, nullable=True)
    week = Column(Integer, nullable=True)
    due_amount = Column(String(50), nullable=True)
    status = Column(String(20), nullable=True)  # received | partial | pending
    paid_amount = Column(String(50), nullable=True)
    payment_date = Column(Date, nullable=True)
    payment_time = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)

    transactions = relationship(
        "FleetHirePaymentTransaction",
        cascade="all, delete-orphan",
        order_by="FleetHirePaymentTransaction.id",
        lazy="selectin",
    )


class FleetHirePaymentTransaction(Base, AuditStampMixin):
    """A single payment made against a weekly schedule row. Multiple transactions
    per week let a hirer split a week's due into several dated part-payments, each
    with its own amount / date / note kept in full history."""
    __tablename__ = "fleet_hire_payment_transaction"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("fleet_hire_payment.id", ondelete="CASCADE"), index=True, nullable=False)
    amount = Column(String(50), nullable=True)
    payment_mode = Column(String(50), nullable=True)  # cash | security_deposit
    payment_date = Column(Date, nullable=True)
    payment_time = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)


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


class FleetHireAudit(Base):
    """Field-level change log for a hire (drives the GDPR screen's Audit Log)."""
    __tablename__ = "fleet_hire_audit"

    id = Column(Integer, primary_key=True, index=True)
    hire_id = Column(Integer, ForeignKey("fleet_hire.id", ondelete="CASCADE"), index=True, nullable=False)
    user = Column(String(200), nullable=True)  # display name of who made the change
    field_changed = Column(String(100), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class FleetHireVehicle(Base, AuditStampMixin):
    """One hire vehicle (a hire can hold many — each swap adds a new one). Holds
    the Hire Vehicle Details + its off-hire checkout."""
    __tablename__ = "fleet_hire_vehicle"

    id = Column(Integer, primary_key=True, index=True)
    hire_id = Column(Integer, ForeignKey("fleet_hire.id", ondelete="CASCADE"), index=True, nullable=False)
    position = Column(Integer, nullable=True)

    vehicle_cost_per_week = Column(String(50), nullable=True)
    deposit = Column(String(50), nullable=True)
    borough = Column(String(100), nullable=True)
    registration_number = Column(String(50), nullable=True)
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    transmission = Column(String(50), nullable=True)
    hire_status = Column(String(20), nullable=True)  # on_hire | off_hire
    swap_car = Column(String(10), nullable=True)
    swap_reason = Column(String(100), nullable=True)
    swap_reason_text = Column(Text, nullable=True)
    hire_start_date = Column(Date, nullable=True)
    hire_start_time = Column(String(20), nullable=True)
    hire_end_date = Column(Date, nullable=True)
    total_hire_period = Column(String(100), nullable=True)
    number_of_weekly_payments = Column(String(20), nullable=True)
    hire_insurance_type = Column(String(100), nullable=True)
    insurance_date_received = Column(Date, nullable=True)
    policy_start_date = Column(Date, nullable=True)
    policy_end_date = Column(Date, nullable=True)
    cross_hire_provider_name = Column(String(200), nullable=True)
    cross_hire_contact_details = Column(String(200), nullable=True)
    cross_hire_rate = Column(String(50), nullable=True)

    # off-hire checkout
    mileage_start = Column(String(50), nullable=True)
    mileage_end = Column(String(50), nullable=True)
    checkout_date = Column(Date, nullable=True)
    checkout_time = Column(String(10), nullable=True)
    checkout_cleanliness = Column(String(50), nullable=True)
    damage_charges = Column(String(50), nullable=True)
    damage_notes = Column(Text, nullable=True)
    additional_charges = Column(String(100), nullable=True)
    additional_charges_reason = Column(Text, nullable=True)

    created_by = Column(Integer, nullable=True)


class FleetVehicleRegister(Base, AuditStampMixin):
    """Reusable Fleet vehicle register. `is_active=True` means the vehicle is
    currently on hire and cannot be selected for a different hire file."""
    __tablename__ = "fleet_vehicle_register"

    id = Column(Integer, primary_key=True, index=True)
    registration_number = Column(String(50), unique=True, index=True, nullable=False)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    transmission = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="false")


class FleetPcn(Base, AuditStampMixin, AuditByMixin):
    """Penalty Charge Notice details for a hire file."""
    __tablename__ = "fleet_pcn"

    id = Column(Integer, primary_key=True, index=True)
    hire_id = Column(Integer, ForeignKey("fleet_hire.id", ondelete="CASCADE"), index=True, nullable=False)
    tenant_id = Column(Integer, index=True, nullable=True)

    council_name = Column(String(200), nullable=True)
    council_address = Column(Text, nullable=True)
    council_postcode = Column(String(20), nullable=True)
    pcn_number = Column(String(100), nullable=True)
    offence_date = Column(Date, nullable=True)
    pcn_status = Column(String(100), nullable=True)
    liability_transfer_status = Column(String(100), nullable=True)
    response_deadline = Column(Date, nullable=True)


class FleetPcnDocument(Base, AuditStampMixin):
    """Document attached to a PCN record."""
    __tablename__ = "fleet_pcn_document"

    id = Column(Integer, primary_key=True, index=True)
    pcn_id = Column(Integer, ForeignKey("fleet_pcn.id", ondelete="CASCADE"), index=True, nullable=False)
    doc_type = Column(String(100), nullable=False)
    filename = Column(String(300), nullable=True)
    s3_key = Column(String(500), nullable=True)
    file_url = Column(Text, nullable=True)
    storage_backend = Column(String(50), nullable=True)
    received_on = Column(Date, nullable=True)
    created_by = Column(Integer, nullable=True)
    uploaded_by = Column(String(200), nullable=True)


class FleetPcnNote(Base, AuditStampMixin):
    """Notes on the PCN screen."""
    __tablename__ = "fleet_pcn_note"

    id = Column(Integer, primary_key=True, index=True)
    pcn_id = Column(Integer, ForeignKey("fleet_pcn.id", ondelete="CASCADE"), index=True, nullable=False)
    note = Column(Text, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_by_name = Column(String(200), nullable=True)


class FleetPcnReminder(Base, AuditStampMixin):
    """Reminder date/time rows for PCN deadlines."""
    __tablename__ = "fleet_pcn_reminder"

    id = Column(Integer, primary_key=True, index=True)
    pcn_id = Column(Integer, ForeignKey("fleet_pcn.id", ondelete="CASCADE"), index=True, nullable=False)
    reminder_type = Column(String(100), nullable=False)
    reminder_date = Column(Date, nullable=True)
    reminder_time = Column(String(10), nullable=True)
    created_by = Column(Integer, nullable=True)
