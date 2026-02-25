# app/schemas/lookups.py
from typing import Optional
from pydantic import BaseModel, Field, PrivateAttr

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