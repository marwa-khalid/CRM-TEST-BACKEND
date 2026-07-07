from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from libdata.models.tables import EngineerDetail, Claim, Address, EngineerCompany
from appflow.models.engineer_detail import EngineerDetailCreate
import re
from datetime import datetime
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType
from appflow.utils import build_case_reference

class EngineerDetailService:

    @staticmethod
    def get_engineer_by_claim_id(claim_id: int, db: Session):
        existing = db.query(EngineerDetail).options(
            joinedload(EngineerDetail.engineer_address),
            joinedload(EngineerDetail.vehicle_address)
        ).filter(EngineerDetail.claim_id == claim_id).first()

        if not existing:
            raise HTTPException(status_code=404, detail="Engineer detail not found")
        return existing

    @staticmethod
    def get_engineer_by_company_name(company_name: str, db: Session):
        existing = db.query(EngineerDetail).options(
            joinedload(EngineerDetail.engineer_address),
            joinedload(EngineerDetail.vehicle_address)
        ).filter(EngineerDetail.company_name == company_name).first()

        if not existing:
            raise HTTPException(status_code=404, detail="Engineer detail not found")
        return existing

    # ── Engineer company master (Company Name autocomplete) ──────────────────
    @staticmethod
    def search_engineer_companies(query: str, db: Session):
        """Suggestions for the engineer Company Name field (name + address)."""
        search = (query or "").strip()
        if not search:
            return []
        rows = (
            db.query(EngineerCompany)
            .filter(EngineerCompany.company_name.ilike(f"%{search}%"))
            .order_by(EngineerCompany.company_name.asc())
            .limit(20)
            .all()
        )
        results, seen = [], set()
        for r in rows:
            name = (r.company_name or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            results.append({"company_name": name, "address": r.address, "postcode": r.postcode})
        return results

    @staticmethod
    def _upsert_engineer_company(db: Session, company_name, address=None, postcode=None):
        """Add a newly-typed engineer company to the master list so it shows up
        in future suggestions. If it already exists, fill in / update its address
        & postcode from what the user entered, so next time this company is
        picked its address auto-fills. Never raises (best-effort)."""
        name = (company_name or "").strip()
        if not name:
            return
        addr = (address or "").strip() or None
        pc = (postcode or "").strip() or None
        try:
            existing = (
                db.query(EngineerCompany)
                .filter(EngineerCompany.company_name.ilike(name))
                .first()
            )
            if existing:
                changed = False
                if addr and addr != existing.address:
                    existing.address = addr
                    changed = True
                if pc and pc != existing.postcode:
                    existing.postcode = pc
                    changed = True
                if changed:
                    db.commit()
                return
            db.add(EngineerCompany(company_name=name, address=addr, postcode=pc))
            db.commit()
        except Exception:
            db.rollback()

    @staticmethod
    def create_engineer(engineer: EngineerDetailCreate, db: Session, tenant_id: int, actor_id: int):
        claim = db.query(Claim).filter(
            Claim.id == engineer.claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        try:
            engineer_data = engineer.dict()

            # Handle nested engineer_address
            engineer_address_data = engineer_data.pop("engineer_address", None)
            if engineer_address_data:
                engineer_address = Address(**engineer_address_data)
                db.add(engineer_address)
                db.flush()  # assigns ID
                engineer_data["engineer_address_id"] = engineer_address.id

            # Handle nested vehicle_address
            vehicle_address_data = engineer_data.pop("vehicle_address", None)
            if vehicle_address_data:
                vehicle_address = Address(**vehicle_address_data)
                db.add(vehicle_address)
                db.flush()
                engineer_data["vehicle_address_id"] = vehicle_address.id

            # Create EngineerDetail
            new_engineer = EngineerDetail(
                **engineer_data,
                tenant_id=tenant_id,
                created_by=actor_id,
                updated_by=actor_id
            )
            db.add(new_engineer)
            db.commit()
            db.refresh(new_engineer)
            # Remember this company for the Company Name autocomplete.
            EngineerDetailService._upsert_engineer_company(
                db,
                new_engineer.company_name,
                (engineer_address_data or {}).get("address"),
                (engineer_address_data or {}).get("postcode"),
            )
            reference = build_case_reference(claim.id,db)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim.id,
                file_name=f"The engineer detail has been created for claim {reference}",
                file_path="",
                file_type=HistoryLogType.CREATED_ENGINEER_DETAIL,
                user_id=actor_id,
                tenant_id=tenant_id
            )

            # Mirror the inspection date onto the calendar; notify only when the
            # engineer report is actually received (uploaded), not on any change.
            EngineerDetailService._sync_inspection_event(db, new_engineer, tenant_id, reference)
            if new_engineer.engineer_report_received:
                EngineerDetailService._notify_report_received(db, claim.id, tenant_id, actor_id)

            return db.query(EngineerDetail).options(
                joinedload(EngineerDetail.engineer_address),
                joinedload(EngineerDetail.vehicle_address)
            ).filter(EngineerDetail.id == new_engineer.id).first()

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creating engineer detail: {str(e)}")

    @staticmethod
    def update_engineer(claim_id: int, engineer: EngineerDetailCreate, db: Session, tenant_id: int, actor_id: int):
        existing = db.query(EngineerDetail).filter(
            EngineerDetail.claim_id == claim_id,
            EngineerDetail.tenant_id == tenant_id
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Engineer detail not found")

        # Ensure claim exists
        claim = db.query(Claim).filter(
            Claim.id == claim_id,
            Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        try:
            # Capture before applying changes so the report notification fires only
            # on the False→True transition (report actually received/uploaded).
            was_received = bool(existing.engineer_report_received)
            engineer_data = engineer.dict(exclude_unset=True)
            changed_fields = []

            # --- Field name mapping for readable labels ---
            field_label_map = {
                "company_name": "Company Name",
                "vehicle_payment_beneficiary": "Vehicle Payment Beneficiary",
                "reference": "Reference",
                "actual_fee": "Actual Fee",
                "invoice_settled_amount": "Invoice Settled Amount",
                "invoice_paid_on": "Invoice Paid On",
                "invoice_settled_on": "Invoice Settled On",
                "invoice_received_on": "Invoice Received On",
                "engineer_report_received": "Engineer Report Received?",
                "engineer_instructed": "Engineer Instructed",
                "inspection_date":"Inspection Date",
                "engineer_report_received_date":"Engineer’s Report Received Date",
                "engineer_fee": "Engineer Fee",
                "site": "Site",
                "engineer_address.address": "Engineer Address",
                "engineer_address.postcode": "Engineer Postcode",
                "engineer_address.mobile_tel": "Engineer Telephone",
                "engineer_address.email": "Engineer Email",
                "vehicle_address.address": "Vehicle Address",
                "vehicle_address.postcode": "Vehicle Postcode",
                "vehicle_address.mobile_tel": "Vehicle Mobile Tel",
                "vehicle_address.email": "Vehicle Email"
            }

            # --- Handle engineer_address ---
            engineer_address_data = engineer_data.pop("engineer_address", None)
            if engineer_address_data:
                if existing.engineer_address:
                    for key, value in engineer_address_data.items():
                        old_value = getattr(existing.engineer_address, key)
                        if old_value != value:
                            changed_fields.append(f"engineer_address.{key}")
                            setattr(existing.engineer_address, key, value)
                else:
                    new_engineer_address = Address(**engineer_address_data)
                    db.add(new_engineer_address)
                    db.flush()
                    existing.engineer_address_id = new_engineer_address.id
                    changed_fields.append("engineer_address")

            # --- Handle vehicle_address ---
            vehicle_address_data = engineer_data.pop("vehicle_address", None)
            if vehicle_address_data:
                if existing.vehicle_address:
                    for key, value in vehicle_address_data.items():
                        old_value = getattr(existing.vehicle_address, key)
                        if old_value != value:
                            changed_fields.append(f"vehicle_address.{key}")
                            setattr(existing.vehicle_address, key, value)
                else:
                    new_vehicle_address = Address(**vehicle_address_data)
                    db.add(new_vehicle_address)
                    db.flush()
                    existing.vehicle_address_id = new_vehicle_address.id
                    changed_fields.append("vehicle_address")

            # --- Update other fields ---
            for key, value in engineer_data.items():
                old_value = getattr(existing, key)
                if old_value != value:
                    changed_fields.append(key)
                    setattr(existing, key, value)
            existing.updated_by = actor_id
            db.commit()
            db.refresh(existing)
            # Remember this company for the Company Name autocomplete.
            EngineerDetailService._upsert_engineer_company(
                db,
                existing.company_name,
                existing.engineer_address.address if existing.engineer_address else None,
                existing.engineer_address.postcode if existing.engineer_address else None,
            )
            if changed_fields:
                readable_changes = [
                    field_label_map.get(field, field) for field in changed_fields
                ]
                file_path = ", ".join(readable_changes)
                reference = build_case_reference(claim_id,db)
                HistoryActivityService.create_activity(
                    db=db,
                    claim_id=claim_id,
                    file_name=f"The engineer detail has been updated for claim {reference}",
                    file_path=file_path,
                    file_type=HistoryLogType.UPDATED_ENGINEER_DETAIL,
                    user_id=actor_id,
                    tenant_id=tenant_id
                )

            # Inspection date → calendar event (create / update / remove on clear).
            _ref = build_case_reference(claim_id, db)
            EngineerDetailService._sync_inspection_event(db, existing, tenant_id, _ref)
            # Notify only when the report just became received (uploaded).
            if existing.engineer_report_received and not was_received:
                EngineerDetailService._notify_report_received(db, claim_id, tenant_id, actor_id)

            return db.query(EngineerDetail).options(
                joinedload(EngineerDetail.engineer_address),
                joinedload(EngineerDetail.vehicle_address)
            ).filter(EngineerDetail.id == existing.id).first()

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error updating engineer detail: {str(e)}")

    @staticmethod
    def _sync_inspection_event(db, engineer, tenant_id, reference=None):
        """Mirror the engineer's inspection date as a system calendar event.
        Auto creates/updates it, and removes it if the date is cleared."""
        try:
            from appflow.services.calendar_event_service import CalendarEventService
            CalendarEventService.sync_system_event(
                db, tenant_id=tenant_id,
                source_type="engineer_inspection", source_ref_id=engineer.id,
                title=f"Engineer Inspection — {reference}" if reference else "Engineer Inspection",
                event_type="Engineer Inspection",
                start_date=engineer.inspection_date,
                claim_id=engineer.claim_id, claim_reference=reference,
            )
        except Exception:
            pass

    @staticmethod
    def _notify_report_received(db, claim_id, tenant_id, actor_id):
        """Fire the 'Engineer Report Uploaded' notification — only when the engineer
        report is actually received/uploaded, not on every field change."""
        if not claim_id:
            return
        try:
            from appflow.services.notification_service import safe_notify
            ref = build_case_reference(claim_id, db)
            safe_notify(
                db, recipient_user_id=actor_id, tenant_id=tenant_id, actor_user_id=actor_id,
                category="Claim", tab="Claims", title="Engineer Report Updated",
                description=f"Engineer report received for {ref}.", claim_id=claim_id,
            )
        except Exception:
            pass

    @staticmethod
    def deactivate_engineer(engineer_id: int, db: Session, tenant_id: int):
        engineer_to_deactivate = db.query(EngineerDetail).filter(
            EngineerDetail.id == engineer_id,
            EngineerDetail.tenant_id == tenant_id
        ).first()

        if not engineer_to_deactivate:
            raise HTTPException(status_code=404, detail="Engineer detail not found")

        try:
            engineer_to_deactivate.is_active = False
            db.commit()
            db.refresh(engineer_to_deactivate)
            return {"detail": "Engineer detail deactivated successfully"}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error deactivating engineer detail: {str(e)}")

    @staticmethod
    def search_engineers(query: str, db: Session, tenant_id: int):
        return db.query(EngineerDetail).options(
            joinedload(EngineerDetail.engineer_address),
            joinedload(EngineerDetail.vehicle_address)
        ).filter(
            EngineerDetail.company_name.ilike(f"%{query}%"),
            EngineerDetail.tenant_id == tenant_id
        ).all()

    @staticmethod
    def extract_engineer_data(text: str):
        """
        Parse engineer document text into structured fields.
        """
        fields = {
            "engineer_instructed": "",
            "inspection_date": "",
            "engineer_report_received_date": "",
            "engineer_fee": "",

            "labour": "",
            "paint_material": "",
            "parts": "",
            "miscellaneous": "",
            "job_hire": "",
            "sub_total": "",
            "vat": "",
            "total_inc_vat": "",

            "pav": "",
            "salvage_amount": "",
            "salvage_category": "",
        }

        if not text:
            return fields

        # Clean & normalize text
        text = (text
                .replace("Paint\nMaterials", "Paint Materials")
                .replace("Specialist\nE", "Specialist E")
                .replace("V.A.T", "VAT")
                .replace("Total Inc\nVAT", "Total Inc VAT")
                .replace("Total Exc\nVAT", "Total Exc VAT")
                .replace("\u200b", "")
                .replace("\u200c", "")
                .replace("\ufeff", "")
                .replace("\u00a0", " ")
                )

        patterns = {
            "engineer_instructed": r"Date\s*Instructed\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
            "inspection_date": r"Date\s*of\s*Inspection\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
            "engineer_report_received_date": r"Date\s*of\s*Report\s*[:\-]?\s*([\d]{1,2}\s+\w+\s+\d{4})",
            "engineer_fee": r"Engineers?\s+Report\s+Fee\s*[:\-]?\s*[£€]?\s*([\d]+\.\d{2})",

            "labour": r"Labour\s*[£€]?\s*([\d]+\.\d{2})",
            "paint_material": r"Paint\s*/?\s*Materials\s*[£€]?\s*([\d]+\.\d{2})",
            "parts": r"Parts\s*[£€]?\s*([\d]+\.\d{2})",
            "miscellaneous": r"Specialist\s*[£€]?\s*([\d]+\.\d{2})",
            "sub_total": r"Total\s+Exc\s+VAT\s*[£€]?\s*([\d]+\.\d{2})",
            "vat": r"VAT\s*@?\s*\d{1,3}\s*%?\s*[\s£€]*([\d]+\.\d{2})",
            "total_inc_vat": r"Total\s+Inc\s+VAT\s*[£€]?\s*([\d]+\.\d{2})",

            "pav": r"Engineers?\s+Valuation\s+Figure\s*[£€]?\s*([\d]+\.\d{2})",
            "salvage_amount": r"Salvage\s+Value\s*[£€]?\s*([\d]+\.\d{2}|\d+)",
            "salvage_category": r"Motor\s+Salvage\s+Category\s*[:\-]?\s*([A-Z])",
        }

        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).replace("£", "").replace("€", "").strip()
                # Convert date fields into dd-mm-yyyy
                if field in ["engineer_instructed", "inspection_date", "engineer_report_received_date","repair_inst"]:
                    try:
                        dt = datetime.strptime(value, "%d %B %Y")  # e.g. 04 July 2025
                        value = dt.strftime("%d-%m-%Y")  # -> 04-07-2025
                    except Exception:
                        pass
                fields[field] = value

        return fields
