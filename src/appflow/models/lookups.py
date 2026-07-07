# app/schemas/lookups.py
from typing import Optional
from pydantic import BaseModel, Field, PrivateAttr
from decimal import Decimal

# ---------- Base DTOs (shared shape) ----------
class LookupBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    sort_order: int = 0
    is_active: bool = True
    _tenant_id: Optional[int] = PrivateAttr(default=None)

class LookupOut(LookupBase):
    id: int
    class Config:
        from_attributes = True  # pydantic v2

# ---------- Per-table DTOs ----------
class ClaimTypeIn(LookupBase): pass
class ClaimTypeOut(LookupOut): pass

class HandlerIn(LookupBase): pass
class HandlerOut(LookupOut): pass

class TargetDebtIn(LookupBase):
    label: str = Field(..., min_length=1, max_length=50)
class TargetDebtOut(LookupOut): pass

class CaseStatusIn(LookupBase):
    label: str = Field(..., min_length=1, max_length=100)
class CaseStatusOut(LookupOut): pass

class SourceChannelIn(LookupBase):
    requires_staff: bool = False
class SourceChannelOut(LookupOut):
    requires_staff: bool

class ProspectIn(LookupBase):
    label: str = Field(..., min_length=1, max_length=100)
class ProspectOut(LookupOut): pass

class PresentFilePositionIn(LookupBase): pass
class PresentFilePositionOut(LookupOut): pass

class LanguageIn(LookupBase): pass
class LanguageOut(LookupOut): pass

class FuelTypeIn(LookupBase):pass
class FuelTypeOut(LookupOut):pass

class TransmissionIn(LookupBase):pass
class TransmissionOut(LookupOut):pass

class TaxiTypeIn(LookupBase):pass
class TaxiTypeOut(LookupOut):pass

class SalvageCategoryIn(LookupBase):pass
class SalvageCategoryOut(LookupOut):pass

class KeepingSalvageIn(LookupBase):pass
class KeepingSalvageOut(LookupOut):pass

class PavAgreeIn(LookupBase):pass
class PavAgreeOut(LookupOut):pass

class RetainingSalvageIn(LookupBase):pass
class RetainingSalvageOut(LookupOut):pass

class PolicyTypeIn(LookupBase):pass
class PolicyTypeOut(LookupOut):pass

class CoverLevelIn(LookupBase):pass
class CoverLevelOut(LookupOut):pass

class ReasonMidIn(LookupBase):pass
class ReasonMidOut(LookupOut):pass

class LiabilityStanceIn(LookupBase):pass
class LiabilityStanceOut(LookupOut):pass

class SettlementStatusIn(LookupBase):pass
class SettlementStatusOut(LookupOut):pass

# Vehicle Status
class VehicleStatusIn(LookupBase): pass
class VehicleStatusOut(LookupOut): pass

class ClientVehicleCategoryIn(LookupBase):pass
class ClientVehicleCategoryOut(LookupOut):pass

class ActualVehicleCategoryIn(LookupBase):
    abi_rate: Decimal
    bhr_rate: Decimal
    fifty_fifty_rate: Optional[Decimal] = None
    valet_rate: Decimal

class ActualVehicleCategoryOut(LookupOut):
    abi_rate: Decimal
    bhr_rate: Decimal
    fifty_fifty_rate: Optional[Decimal] = None
    valet_rate: Decimal

class AdminFeeTypeIn(LookupBase):pass
class AdminFeeTypeOut(LookupOut):pass

class HireVehicleStatusIn(LookupBase):pass
class HireVehicleStatusOut(LookupOut):pass
