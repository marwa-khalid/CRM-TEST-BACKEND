"""Pydantic schemas for the Fleet module."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class HireUpdate(BaseModel):
    """Partial update — every field optional so the client can field-level PATCH.
    Only fields explicitly sent are applied (see service, exclude_unset)."""
    # General Details
    file_closed_at: Optional[datetime] = None
    insurance_type: Optional[str] = None
    rental_advisor: Optional[str] = None
    current_position: Optional[str] = None
    hirer_type: Optional[str] = None
    taxi_badge_number: Optional[str] = None
    taxi_badge_name: Optional[str] = None
    taxi_badge_expiry: Optional[date] = None
    taxi_badge_council: Optional[str] = None
    taxi_badge_type: Optional[str] = None
    bank_name: Optional[str] = None
    account_name: Optional[str] = None
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    # Driver Details
    driver_name: Optional[str] = None
    driver_address: Optional[str] = None
    driver_postcode: Optional[str] = None
    driver_email: Optional[str] = None
    driver_telephone: Optional[str] = None
    driver_mobile: Optional[str] = None
    driving_licence_number: Optional[str] = None
    national_insurance_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    driving_licence_start: Optional[date] = None
    driving_licence_end: Optional[date] = None
    # GDPR & Marketing
    where_found: Optional[str] = None
    privacy_notice_explained: Optional[str] = None
    privacy_notice_date: Optional[date] = None
    privacy_notice_method: Optional[str] = None
    lawful_basis: Optional[str] = None
    email_consent: Optional[str] = None
    email_consent_date: Optional[date] = None
    email_consent_method: Optional[str] = None
    sms_consent: Optional[str] = None
    phone_consent: Optional[str] = None
    postal_consent: Optional[str] = None
    reason_for_withdrawal: Optional[str] = None
    # Hire Vehicle Details (screen 5)
    vehicle_cost_per_week: Optional[str] = None
    deposit: Optional[str] = None
    borough: Optional[str] = None
    registration_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    transmission: Optional[str] = None
    hire_status: Optional[str] = None
    swap_car: Optional[str] = None
    swap_reason: Optional[str] = None
    swap_reason_text: Optional[str] = None
    hire_start_date: Optional[date] = None
    hire_start_time: Optional[str] = None
    hire_end_date: Optional[date] = None
    total_hire_period: Optional[str] = None
    hire_insurance_type: Optional[str] = None
    insurance_date_received: Optional[date] = None
    policy_start_date: Optional[date] = None
    policy_end_date: Optional[date] = None
    cross_hire_provider_name: Optional[str] = None
    cross_hire_contact_details: Optional[str] = None
    cross_hire_rate: Optional[str] = None
    payment_hire_start_date: Optional[date] = None
    payment_hire_end_date: Optional[date] = None
    vehicle_cost_per_day: Optional[str] = None
    number_of_weekly_payments: Optional[str] = None
    payment_day: Optional[str] = None
    security_deposit: Optional[str] = None
    weekly_hire_payment: Optional[str] = None
    total_planned_hire_cost: Optional[str] = None
    initial_amount_due: Optional[str] = None
    payment_damage_charges: Optional[str] = None
    additional_charges: Optional[str] = None


class HireDocumentResponse(BaseModel):
    id: int
    doc_type: str
    filename: Optional[str] = None
    file_url: Optional[str] = None
    received_on: Optional[date] = None
    created_at: Optional[datetime] = None
    extracted_address: Optional[str] = None

    class Config:
        from_attributes = True


class GeneratedDocumentFileResponse(BaseModel):
    key: str
    filename: str
    content_type: str
    size: int


class HireAuditResponse(BaseModel):
    id: int
    user: Optional[str] = None
    field_changed: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HireResponse(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    fleet_reference: Optional[str] = None
    file_opened_at: Optional[datetime] = None
    file_closed_at: Optional[datetime] = None
    insurance_type: Optional[str] = None
    rental_advisor: Optional[str] = None
    current_position: Optional[str] = None
    hirer_type: Optional[str] = None
    taxi_badge_number: Optional[str] = None
    taxi_badge_name: Optional[str] = None
    taxi_badge_expiry: Optional[date] = None
    taxi_badge_council: Optional[str] = None
    taxi_badge_type: Optional[str] = None
    bank_name: Optional[str] = None
    account_name: Optional[str] = None
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    driver_name: Optional[str] = None
    driver_address: Optional[str] = None
    driver_postcode: Optional[str] = None
    driver_email: Optional[str] = None
    driver_telephone: Optional[str] = None
    driver_mobile: Optional[str] = None
    driving_licence_number: Optional[str] = None
    national_insurance_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    driving_licence_start: Optional[date] = None
    driving_licence_end: Optional[date] = None
    where_found: Optional[str] = None
    privacy_notice_explained: Optional[str] = None
    privacy_notice_date: Optional[date] = None
    privacy_notice_method: Optional[str] = None
    lawful_basis: Optional[str] = None
    email_consent: Optional[str] = None
    email_consent_date: Optional[date] = None
    email_consent_method: Optional[str] = None
    sms_consent: Optional[str] = None
    phone_consent: Optional[str] = None
    postal_consent: Optional[str] = None
    reason_for_withdrawal: Optional[str] = None
    vehicle_cost_per_week: Optional[str] = None
    deposit: Optional[str] = None
    borough: Optional[str] = None
    registration_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    transmission: Optional[str] = None
    hire_status: Optional[str] = None
    swap_car: Optional[str] = None
    swap_reason: Optional[str] = None
    swap_reason_text: Optional[str] = None
    hire_start_date: Optional[date] = None
    hire_start_time: Optional[str] = None
    hire_end_date: Optional[date] = None
    total_hire_period: Optional[str] = None
    hire_insurance_type: Optional[str] = None
    insurance_date_received: Optional[date] = None
    policy_start_date: Optional[date] = None
    policy_end_date: Optional[date] = None
    cross_hire_provider_name: Optional[str] = None
    cross_hire_contact_details: Optional[str] = None
    cross_hire_rate: Optional[str] = None
    payment_hire_start_date: Optional[date] = None
    payment_hire_end_date: Optional[date] = None
    vehicle_cost_per_day: Optional[str] = None
    number_of_weekly_payments: Optional[str] = None
    payment_day: Optional[str] = None
    security_deposit: Optional[str] = None
    weekly_hire_payment: Optional[str] = None
    total_planned_hire_cost: Optional[str] = None
    initial_amount_due: Optional[str] = None
    payment_damage_charges: Optional[str] = None
    additional_charges: Optional[str] = None
    # Derived (list view): the most recently added vehicle on the Hire Vehicle Details
    # screen — drives the On/Off Hire listing widgets and the listing's Vehicle Reg column.
    last_vehicle_hire_status: Optional[str] = None
    last_vehicle_registration: Optional[str] = None

    class Config:
        from_attributes = True


class HireCompletionSummary(BaseModel):
    vehicle_present: int = 0
    vehicle_total: int = 5
    proof_present: int = 0
    proof_total: int = 3
    document_present: int = 0
    document_total: int = 8
    pcn_present: int = 0
    pcn_total: int = 8


class VehicleUpdate(BaseModel):
    """Partial update for one hire vehicle (field-level save)."""
    vehicle_cost_per_week: Optional[str] = None
    deposit: Optional[str] = None
    borough: Optional[str] = None
    registration_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    transmission: Optional[str] = None
    hire_status: Optional[str] = None
    swap_car: Optional[str] = None
    swap_reason: Optional[str] = None
    swap_reason_text: Optional[str] = None
    hire_start_date: Optional[date] = None
    hire_start_time: Optional[str] = None
    hire_end_date: Optional[date] = None
    total_hire_period: Optional[str] = None
    number_of_weekly_payments: Optional[str] = None
    hire_insurance_type: Optional[str] = None
    insurance_date_received: Optional[date] = None
    policy_start_date: Optional[date] = None
    policy_end_date: Optional[date] = None
    cross_hire_provider_name: Optional[str] = None
    cross_hire_contact_details: Optional[str] = None
    cross_hire_rate: Optional[str] = None
    mileage_start: Optional[str] = None
    mileage_end: Optional[str] = None
    checkout_date: Optional[date] = None
    checkout_time: Optional[str] = None
    checkout_cleanliness: Optional[str] = None
    damage_charges: Optional[str] = None
    damage_notes: Optional[str] = None
    additional_charges: Optional[str] = None
    additional_charges_reason: Optional[str] = None


class VehicleResponse(VehicleUpdate):
    id: int
    hire_id: int
    position: Optional[int] = None

    class Config:
        from_attributes = True


class FleetVehicleRegisterResponse(BaseModel):
    id: int
    registration_number: str
    make: str
    model: str
    transmission: Optional[str] = None
    is_active: bool = False

    class Config:
        from_attributes = True


class FleetVehicleRegisterUpsert(BaseModel):
    registration_number: str
    make: Optional[str] = None
    model: Optional[str] = None
    transmission: Optional[str] = None


class PcnUpdate(BaseModel):
    council_name: Optional[str] = None
    council_address: Optional[str] = None
    council_postcode: Optional[str] = None
    pcn_number: Optional[str] = None
    offence_date: Optional[date] = None
    pcn_status: Optional[str] = None
    liability_transfer_status: Optional[str] = None
    response_deadline: Optional[date] = None


class PcnResponse(PcnUpdate):
    id: int
    hire_id: int
    tenant_id: Optional[int] = None

    class Config:
        from_attributes = True


class PcnDocumentResponse(BaseModel):
    id: int
    doc_type: str
    filename: Optional[str] = None
    file_url: Optional[str] = None
    received_on: Optional[date] = None
    uploaded_by: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PcnNoteCreate(BaseModel):
    note: str


class PcnNoteResponse(BaseModel):
    id: int
    note: str
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PcnReminderUpdate(BaseModel):
    reminder_date: Optional[date] = None
    reminder_time: Optional[str] = None


class PcnReminderResponse(PcnReminderUpdate):
    id: int
    reminder_type: str

    class Config:
        from_attributes = True


class ScheduleSync(BaseModel):
    count: int
    due_amount: Optional[str] = None
    initial_due_amount: Optional[str] = None


class PaymentUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    week: Optional[int] = None
    due_amount: Optional[str] = None
    status: Optional[str] = None
    paid_amount: Optional[str] = None
    payment_date: Optional[date] = None
    payment_time: Optional[str] = None
    notes: Optional[str] = None


class PaymentTransactionCreate(BaseModel):
    """A single dated payment recorded against a weekly schedule row."""
    amount: str
    payment_mode: Optional[str] = "cash"
    payment_date: Optional[date] = None
    payment_time: Optional[str] = None
    notes: Optional[str] = None


class PaymentTransactionUpdate(BaseModel):
    """Edit an existing payment — every field optional; only sent fields apply."""
    amount: Optional[str] = None
    payment_mode: Optional[str] = None
    payment_date: Optional[date] = None
    payment_time: Optional[str] = None
    notes: Optional[str] = None


class PaymentTransactionResponse(BaseModel):
    id: int
    payment_id: int
    amount: Optional[str] = None
    payment_mode: Optional[str] = None
    payment_date: Optional[date] = None
    payment_time: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaymentResponse(PaymentUpdate):
    id: int
    hire_id: int
    transactions: List[PaymentTransactionResponse] = []

    class Config:
        from_attributes = True


class FleetWhatsAppRequest(BaseModel):
    mobile: Optional[str] = None
    message: str
    correspondent: Optional[str] = None
    reference: Optional[str] = None
    phrase: Optional[str] = None
    history_details: Optional[str] = None
    kind: Optional[str] = None


class FleetWhatsAppResponse(BaseModel):
    status: str
    provider: Optional[str] = None
    to: Optional[str] = None
    sid: Optional[str] = None
    message_id: Optional[str] = None
    detail: Optional[str] = None


class DepositRefundRequest(BaseModel):
    """Editable inputs for the structured deposit-refund email; the rest of the
    data (ref, hirer, bank, hire dates, deposit) comes from the hire record."""
    to: str
    cc: Optional[str] = None
    subject: Optional[str] = "Request Refund Deposit"
    ref: Optional[str] = None
    hirer_name: Optional[str] = None
    registration: Optional[str] = None
    deposit: Optional[str] = None
    valeting_fee: Optional[str] = "0"
    vehicle_damages: Optional[str] = None  # defaults to the hire's damage charges
    additional_charges: Optional[str] = None
    excess_ppm: Optional[str] = "0"
    hire_charges_unpaid: Optional[str] = "0"
    adjusted_from_deposit: Optional[str] = None
    charges_due: Optional[str] = None
    total_deductions: Optional[str] = None
    refund_amount: Optional[str] = None
    bank: Optional[str] = None
    account_name: Optional[str] = None
    sort_code: Optional[str] = None
    account_number: Optional[str] = None
    hire_start: Optional[str] = None
    hire_end: Optional[str] = None


class PayHirerRequest(BaseModel):
    """Editable inputs for the structured Pay/Reimburse Hirer email."""
    to: str
    cc: Optional[str] = None
    subject: Optional[str] = None
    amount: str
    reason: str
    registration: Optional[str] = None


class OnHireEmailRequest(BaseModel):
    """Inputs for the structured On-Hire confirmation email. The hirer name comes
    from the hire record; the vehicle fields come from the selected vehicle."""
    to: str
    cc: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    registration: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    hire_start: Optional[str] = None


# --------------------------------------------------------------------------- #
# Vehicle records (Fleet vehicle asset wizard)
# --------------------------------------------------------------------------- #
class VehicleRecordUpdate(BaseModel):
    """Field-level PATCH — every field optional so the client can save one at a time."""
    obtained_for_purpose: Optional[str] = None
    contract_type: Optional[str] = None
    company_owned_or_leased: Optional[bool] = None
    cross_hired_to_us: Optional[bool] = None
    registration_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    variant: Optional[str] = None
    number_of_doors: Optional[str] = None
    number_of_seats: Optional[str] = None
    body_type: Optional[str] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    engine_size_cc: Optional[str] = None
    v5c_document_reference: Optional[str] = None
    chassis_number: Optional[str] = None
    date_of_first_registration: Optional[date] = None
    date_delivered: Optional[date] = None
    vehicle_status: Optional[str] = None
    depot_branch: Optional[str] = None
    road_tax_renewed_on: Optional[date] = None
    purchaser_name: Optional[str] = None
    purchaser_address: Optional[str] = None
    purchaser_postcode: Optional[str] = None
    purchaser_telephone: Optional[str] = None
    purchaser_email: Optional[str] = None
    vehicle_sold_on: Optional[date] = None
    sold_for_inc_vat: Optional[str] = None
    sold_for_exc_vat: Optional[str] = None


class VehicleRecordResponse(VehicleRecordUpdate):
    id: int
    # Calculated server-side as one year after road_tax_renewed_on (read-only).
    road_tax_expiry_date: Optional[date] = None
    # Section C — read-only, pulled from the Skyline (client-side) hire screens.
    latest_mileage_obtained: Optional[str] = None
    mileage_obtained_on: Optional[date] = None

    class Config:
        from_attributes = True


class LicensingAuthorityUpdate(BaseModel):
    """Field-level PATCH for one licensing authority."""
    licensing_authority: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None
    telephone: Optional[str] = None
    contact_number: Optional[str] = None
    email_address: Optional[str] = None
    plate_number: Optional[str] = None
    plating_start_date: Optional[date] = None
    plating_expiry_date: Optional[date] = None
    plating_booked_date: Optional[date] = None
    plating_booked_time: Optional[str] = None
    plating_attended_passed: Optional[bool] = None
    mot_centre_name: Optional[str] = None
    mot_address: Optional[str] = None
    mot_postcode: Optional[str] = None
    mot_telephone: Optional[str] = None
    mot_email_address: Optional[str] = None
    last_mot_date: Optional[date] = None
    mot_expiry_date: Optional[date] = None
    mot_booked_date: Optional[date] = None
    mot_booked_time: Optional[str] = None
    mot_attended_passed: Optional[bool] = None


class LicensingAuthorityResponse(LicensingAuthorityUpdate):
    id: int
    vehicle_record_id: int
    position: Optional[int] = None
    plating_certificate_name: Optional[str] = None
    plating_certificate_url: Optional[str] = None
    mot_certificate_name: Optional[str] = None
    mot_certificate_url: Optional[str] = None

    class Config:
        from_attributes = True


class VehicleServiceUpdate(BaseModel):
    """Field-level PATCH for one servicing record."""
    garage_name: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    service_booked_date: Optional[date] = None
    service_booked_time: Optional[str] = None
    serviced_at_mileage: Optional[str] = None
    serviced_on: Optional[date] = None
    next_service_due_at: Optional[str] = None
    case_reference: Optional[str] = None


class VehicleServiceResponse(VehicleServiceUpdate):
    id: int
    vehicle_record_id: int
    position: Optional[int] = None
    invoice_name: Optional[str] = None
    invoice_url: Optional[str] = None

    class Config:
        from_attributes = True


class AppointmentPassedEmailRequest(BaseModel):
    """Plating / MOT "appointment passed" confirmation. Everything else is read
    from the licensing authority record so the email can't drift from the data."""
    to: Optional[str] = None
    cc: Optional[str] = None
    subject: Optional[str] = None
