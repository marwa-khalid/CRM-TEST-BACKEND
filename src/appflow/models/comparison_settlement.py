from pydantic import BaseModel
from typing import Optional, List


class ComparisonSettlementIn(BaseModel):
    claim_id: int
    # hire_vehicle_provides id when stored per vehicle; None = claim-level row.
    hire_vehicle_id: Optional[int] = None
    settlement_status: Optional[str] = None
    abi_rate_band: Optional[str] = None
    agreed_hire_days: Optional[float] = None
    agreed_hire_rate: Optional[float] = None
    agreed_storage_days: Optional[float] = None
    agreed_storage_rate: Optional[float] = None
    agreed_cdw_days: Optional[float] = None
    agreed_cdw_rate: Optional[float] = None
    agreed_additional_fees: Optional[float] = None
    agreed_penalties: Optional[float] = None
    agreed_repair_rate: Optional[float] = None
    agreed_recovery_rate: Optional[float] = None
    agreed_engineer_rate: Optional[float] = None
    agreed_plating_rate: Optional[float] = None
    agreed_cd_fee: Optional[float] = None
    agreed_admin: Optional[float] = None
    vat_recovered: Optional[bool] = None
    reason_for_reduction: Optional[str] = None


class ComparisonSettlementOut(ComparisonSettlementIn):
    id: int

    class Config:
        from_attributes = True


class SystemValues(BaseModel):
    hire_days: float
    hire_rate_per_day: float
    hire_costs: float
    admin_fee: float
    storage: float
    storage_days: float
    storage_rate_per_day: float
    repair: float
    recovery: float
    plating: float
    engineer_fee: float
    cdw: float
    cdw_days: float
    cd_fee: float


class ComparisonSettlementGetOut(BaseModel):
    # `saved` is the row for the requested vehicle (or the claim-level row).
    # `saved_all` is every saved row for the claim, so the frontend can sum the
    # agreed hire across vehicles for the (display-once) totals.
    saved: Optional[ComparisonSettlementOut] = None
    saved_all: List[ComparisonSettlementOut] = []
    system: SystemValues


class DifferenceEmailIn(BaseModel):
    claim_id: int
    # Optional: when omitted, the API uses the logged-in user's email (derived
    # server-side from the auth cookie, like notify-manager).
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    actual_amount: float
    amount_received: float
    outstanding_difference: float
    write_off_amount: Optional[float] = None
    payment_reason: Optional[str] = None
