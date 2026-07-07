import os
import base64
from html import escape as _escape
from fastapi import HTTPException
from sqlalchemy.orm import Session
from libdata.models.tables import (
    ComparisonSettlement, HireDetail, Storage, Recovery,
    RouteRepair, PlatingAdditionalCharges, EngineerDetail,
)
from appflow.models.comparison_settlement import ComparisonSettlementIn
from appflow.utils import build_case_reference
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId,
)

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "logo.png")
try:
    with open(_LOGO_PATH, "rb") as _lf:
        _LOGO_ENCODED = base64.b64encode(_lf.read()).decode()
except Exception:
    _LOGO_ENCODED = ""

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5174")


def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


class ComparisonSettlementService:

    @staticmethod
    def get_by_claim(claim_id: int, db: Session, vehicle_id: int = None):
        # Return the row for a specific hire vehicle, or the claim-level row
        # (hire_vehicle_id IS NULL) when no vehicle is given.
        q = db.query(ComparisonSettlement).filter(
            ComparisonSettlement.claim_id == claim_id,
            ComparisonSettlement.is_active == True,
            ComparisonSettlement.is_deleted == False,
        )
        if vehicle_id is not None:
            q = q.filter(ComparisonSettlement.hire_vehicle_id == vehicle_id)
        else:
            q = q.filter(ComparisonSettlement.hire_vehicle_id.is_(None))
        return q.first()

    @staticmethod
    def get_all_by_claim(claim_id: int, db: Session):
        return (
            db.query(ComparisonSettlement)
            .filter(
                ComparisonSettlement.claim_id == claim_id,
                ComparisonSettlement.is_active == True,
                ComparisonSettlement.is_deleted == False,
            )
            .all()
        )

    @staticmethod
    def get_system_values(claim_id: int, db: Session) -> dict:
        hire = (
            db.query(HireDetail)
            .filter(HireDetail.claim_id == claim_id, HireDetail.is_deleted == False)
            .first()
        )
        hire_days = _f(
            hire.final_total_no_of_hire_days or hire.no_of_days_hire_so_far if hire else None
        )
        hire_rate = _f(hire.abi_hire_charge_per_day if hire else None)
        admin_fee = _f(hire.abi_administration_fee if hire else None)
        cdw = _f(hire.cdw_charges if hire else None)
        cd_fee = _f(hire.collection_delivery_fee if hire else None)

        storages = (
            db.query(Storage)
            .filter(Storage.claim_id == claim_id, Storage.is_deleted == False)
            .all()
        )
        total_storage = sum(_f(s.total_storage_charges) for s in storages)
        storage_days = sum(_f(s.total_storage_days) for s in storages)
        storage_rate_per_day = total_storage / storage_days if storage_days > 0 else 0.0

        repair = (
            db.query(RouteRepair)
            .filter(RouteRepair.claim_id == claim_id, RouteRepair.is_deleted == False)
            .first()
        )
        repair_cost = _f(repair.total_inc_vat if repair else None)

        recoveries = (
            db.query(Recovery)
            .filter(Recovery.claim_id == claim_id, Recovery.is_deleted == False)
            .all()
        )
        total_recovery = sum(_f(r.recovery_charges) for r in recoveries)

        plating = (
            db.query(PlatingAdditionalCharges)
            .filter(PlatingAdditionalCharges.claim_id == claim_id, PlatingAdditionalCharges.is_deleted == False)
            .first()
        )
        plating_cost = _f(plating.total_plating_cost if plating else None)

        engineer = (
            db.query(EngineerDetail)
            .filter(EngineerDetail.claim_id == claim_id, EngineerDetail.is_deleted == False)
            .first()
        )
        engineer_fee = _f(engineer.engineer_fee if engineer else None)

        return {
            "hire_days": hire_days,
            "hire_rate_per_day": hire_rate,
            "hire_costs": hire_days * hire_rate,
            "admin_fee": admin_fee,
            "storage": total_storage,
            "storage_days": storage_days,
            "storage_rate_per_day": storage_rate_per_day,
            "repair": repair_cost,
            "recovery": total_recovery,
            "plating": plating_cost,
            "engineer_fee": engineer_fee,
            "cdw": cdw,
            "cdw_days": hire_days,
            "cd_fee": cd_fee,
        }

    @staticmethod
    def save(payload: ComparisonSettlementIn, db: Session, current_user: int):
        existing = ComparisonSettlementService.get_by_claim(
            payload.claim_id, db, payload.hire_vehicle_id
        )
        if existing:
            for k, v in payload.model_dump(exclude={"claim_id"}).items():
                setattr(existing, k, v)
            existing.updated_by = current_user
            db.commit()
            db.refresh(existing)
            return existing
        record = ComparisonSettlement(
            **payload.model_dump(),
            created_by=current_user,
            updated_by=current_user,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def send_difference_email(payload, db: Session):
        """Notify the handler that the amount received is less than the actual payable amount."""
        if not payload.recipient_email:
            raise HTTPException(400, "No recipient email provided")

        case_ref = build_case_reference(payload.claim_id, db)
        first_name = "Ruby"  # manager greeting is always "Hi Ruby"
        # Deep-link straight to this case's payment section (first screen)
        view_case_url = f"{FRONTEND_BASE_URL}/add-claim/{payload.claim_id}?mode=payment"
        reason = (getattr(payload, "payment_reason", None) or "").strip()
        reason_html = _escape(reason) if reason else "<span style='color:#98A2B3;'>&mdash;</span>"

        def money(val) -> str:
            try:
                return f"{float(val):,.2f}"
            except Exception:
                return "0.00"

        def row(label: str, value: str, highlight: bool = False) -> str:
            bg = "background:#FDECC8;border-radius:6px;" if highlight else ""
            return f"""
            <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;{bg}">
              <div style="font-size:14px;color:#475467;font-weight:400;">{label}</div>
              <div style="font-size:14px;color:#101828;font-weight:600;">{value}</div>
            </div>"""

        def divider() -> str:
            return '<div style="height:1px;background:#EAECF0;width:100%;"></div>'

        html = f"""
        <div style="font-family:Arial,sans-serif;background:#fff;padding:30px 20px;color:#475467;max-width:640px;margin:0 auto;">
          <div style="text-align:center;margin-bottom:20px;">
            <img src="cid:companylogo" alt="Logo" style="width:48px;">
          </div>

          <div style="text-align:center;font-size:18px;font-weight:700;color:#101828;margin-bottom:16px;">
            Hi {first_name}
          </div>

          <div style="max-width:384px;margin:0 auto 24px auto;text-align:center;font-size:14px;color:#475467;line-height:1.6;">
            Please note that the amount received against the below case is less than the actual payable amount.
          </div>

          <div style="border:1px solid #EAECF0;border-radius:8px;padding:8px;max-width:384px;margin:0 auto 24px auto;">
            {row("Case Number:", case_ref)}
            {divider()}
            {row("Actual Amount (inc)", f"&pound; {money(payload.actual_amount)}")}
            {divider()}
            {row("Amount Received", f"&pound; {money(payload.amount_received)}")}
            {row("Outstanding Difference (inc)", f"&pound; {money(payload.outstanding_difference)}", highlight=True)}
            {divider()}
            {row("Write off Amount", f"&pound; {money(payload.write_off_amount)}")}
          </div>

          <div style="max-width:384px;margin:0 auto 24px auto;">
            <div style="text-align:center;font-size:14px;color:#475467;margin-bottom:8px;">
              Payment Reason / Miscellaneous Notes
            </div>
            <div style="text-align:center;border:1px solid #EAECF0;border-radius:8px;padding:16px;min-height:80px;
                        font-size:13px;color:#98A2B3;line-height:1.6;white-space:pre-wrap;">{reason_html}</div>
          </div>

          <div style="text-align:center;font-size:14px;color:#475467;margin-bottom:24px;">
            Please review the case accordingly
          </div>

          <div style="text-align:center;margin-bottom:24px;">
            <a href="{view_case_url}" target="_blank" rel="noopener noreferrer"
               style="display:inline-block;background:#0352FD;color:#fff;text-decoration:none;
               font-size:16px;font-weight:600;padding:14px 36px;border-radius:4px;">View Case</a>
          </div>

          <div style="max-width:580px;height:1px;background:#EAECF0;margin:20px auto;"></div>

          <div style="text-align:center;">
            <p style="font-size:12px;font-weight:600;color:#101828;margin:0;">Kind regards,</p>
            <p style="font-size:14px;font-weight:600;color:#101828;margin:4px 0;">Nationwide Assist&nbsp;&nbsp;IT / Systems Team</p>
          </div>
        </div>
        """

        # Graph-first so it reaches Outlook (logo auto-attached via cid:companylogo);
        # SendGrid fallback.
        from appflow.services.email_delivery import send_email as deliver_email

        result = deliver_email(
            to=payload.recipient_email,
            subject=f"Outstanding Difference on Settlement – {case_ref}",
            html=html,
        )
        if result.get("status") != "sent":
            raise HTTPException(500, f"Email send failed: {result.get('detail')}")
        return {"status": "sent", "delivery": result}
