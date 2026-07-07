from typing import List
from fastapi import HTTPException,Request
from sqlalchemy.orm import Session
from libdata.models.tables import (
    DriverCheck, HireVehicleProvided, DriverCheckImage, HistoryActivities,
    ClientDetail, Address, Referrer, VehicleDetail, Claim,
)
from appflow.models.driver_check import DriverCheckBulkCreate, DriverCheckImageOut, DriverCheckCreate
import os
import base64
from libdata.enums import DriverCheckImageType, HistoryLogType
from fastapi import File, UploadFile, Query
from datetime import datetime
from sqlalchemy.orm import joinedload
from appflow.services.history_activity_service import HistoryActivityService
from appflow.services.graph_email_service import GraphEmailService
from appflow.utils import build_case_reference
from appflow.logger import logger
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "logo.png")
try:
    with open(_LOGO_PATH, "rb") as _lf:
        _LOGO_ENCODED = base64.b64encode(_lf.read()).decode()
except Exception:
    _LOGO_ENCODED = ""

class DriverCheckService:
    @staticmethod
    def _validate_driver_check(check_data):
        if check_data.interior_damage_at_check_in and not check_data.describe_interior_damage:
            raise HTTPException(
                status_code=400,
                detail="describe_interior_damage is required when interior_damage_at_check_in is True",
            )

        if check_data.exterior_damage_at_check_in and not check_data.describe_exterior_damage:
            raise HTTPException(
                status_code=400,
                detail="describe_exterior_damage is required when exterior_damage_at_check_in is True",
            )

        if check_data.apply_petrol_checkout_charges and check_data.petrol_checkout_charges is None:
            raise HTTPException(
                status_code=400,
                detail="petrol_checkout_charges is required when apply_petrol_checkout_charges is True",
            )

        if check_data.apply_damage_charges and check_data.damage_charges is None:
            raise HTTPException(
                status_code=400,
                detail="damage_charges is required when apply_damage_charges is True",
            )

    @staticmethod
    def _attach_registration_number(records, db: Session):
        """
        Attach registration_number from HireVehicleProvided to DriverCheck records.
        Works for both single object and list.
        """

        def attach_single(record):
            if not record:
                return None
            hire_vehicle = db.query(HireVehicleProvided).filter(
                HireVehicleProvided.id == record.hire_vehicle_provided_id
            ).first()
            record.registration_number = hire_vehicle.hire_vehicle_registration if hire_vehicle else None
            return record

        if isinstance(records, list):
            return [attach_single(r) for r in records]
        return attach_single(records)

    # ----- CREATE -----
    @staticmethod
    def create_driver_checks(payload: DriverCheckBulkCreate, db: Session, current_user: int,image_type,files):
        # ✅ Check that HireVehicleProvided exists and has hire_start_date
        hire_vehicle = db.query(HireVehicleProvided).filter(
            HireVehicleProvided.id == payload.hire_vehicle_provided_id,
            HireVehicleProvided.claim_id == payload.claim_id
        ).first()

        if not hire_vehicle:
            raise HTTPException(status_code=404, detail="Hire vehicle not found for this claim")

        if not hire_vehicle.hire_start_date:
            raise HTTPException(status_code=400,
                                detail="Hire vehicle must have a hire_start_date before creating driver checks")

        created_records = []

        for check_data in payload.driver_checks:
            DriverCheckService._validate_driver_check(check_data)

            new_check = DriverCheck(
                **check_data.dict(),
                claim_id=payload.claim_id,
                hire_vehicle_provided_id=payload.hire_vehicle_provided_id,  # 🔗 Link added
                created_by=current_user,
                updated_by=current_user,
            )
            db.add(new_check)

            db.flush()
            DriverCheckService.save_driver_check_images(new_check.id,image_type,files)

            created_records.append(new_check)

        db.commit()
        for record in created_records:
            db.refresh(record)

        created_records = DriverCheckService._attach_registration_number(created_records, db)
        return created_records

    @staticmethod
    def get_driver_checks_by_claim(claim_id: int, db: Session, request: Request = None) -> List[DriverCheck]:
        records = db.query(DriverCheck).filter(DriverCheck.claim_id == claim_id, DriverCheck.is_active == True).all()
        if not records:
            return []
        records = DriverCheckService._attach_registration_number(records, db)
        # Populate saved interior/exterior images (with URLs) so the checkout form
        # can show previously uploaded photos when it is reopened.
        for rec in records:
            rec.interior_images = [
                DriverCheckImageOut.from_orm(img, request)
                for img in rec.images
                if img.image_type == DriverCheckImageType.INTERIOR
            ]
            rec.exterior_images = [
                DriverCheckImageOut.from_orm(img, request)
                for img in rec.images
                if img.image_type == DriverCheckImageType.EXTERIOR
            ]
        return records

    @staticmethod
    def deactivate_hire_vehicle(hire_vehicle_provided_id: int, db: Session):
        record = (
            db.query(DriverCheck)
            .filter(DriverCheck.hire_vehicle_provided_id == hire_vehicle_provided_id)
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=404,
                detail="Hire vehicle record not found"
            )
        if not hasattr(record, "is_active") or not hasattr(record, "is_deleted"):
            raise HTTPException(
                status_code=400,
                detail="'is_active' or 'is_delete' column missing in HireVehicleProvided"
            )
        record.is_active = False
        record.is_deleted = True

        db.commit()
        db.refresh(record)
        return {"detail": f"Hire vehicle record {hire_vehicle_provided_id} deactivated and marked as deleted"}

    @staticmethod
    def deactivate_driver_checks_by_claim(claim_id: int, db: Session):
        records = db.query(DriverCheck).filter(DriverCheck.claim_id == claim_id).all()
        if not records:
            raise HTTPException(status_code=404, detail="No driver checks found for this claim")

        for record in records:
            if hasattr(record, "is_active"):
                record.is_active = False
            else:
                raise HTTPException(
                    status_code=400,
                    detail="DriverCheck table does not have 'is_active' column for deactivation",
                )

        db.commit()
        return {"detail": f"{len(records)} driver check(s) deactivated for claim {claim_id}"}

    @staticmethod
    def update_driver_check_by_hire_vehicle(
            hire_vehicle_provided_id: int,
            payload,
            db: Session,
            current_user: int
    ):
        hire_vehicle = (
            db.query(HireVehicleProvided)
            .filter(HireVehicleProvided.id == hire_vehicle_provided_id)
            .first()
        )
        if not hire_vehicle:
            raise HTTPException(status_code=404, detail="Hire vehicle not found")

        if not hire_vehicle.hire_start_date:
            raise HTTPException(
                status_code=400,
                detail="Cannot update Driver Check — hire vehicle has no hire_start_date"
            )

        driver_check = (
            db.query(DriverCheck)
            .filter(DriverCheck.claim_id == hire_vehicle.claim_id)
            .first()
        )
        if not driver_check:
            raise HTTPException(status_code=404, detail="Driver Check not found for this hire vehicle")

        DriverCheckService._validate_driver_check(payload)

        for key, value in payload.dict().items():
            if hasattr(driver_check, key):
                setattr(driver_check, key, value)

        driver_check.updated_by = current_user
        db.commit()
        db.refresh(driver_check)

        driver_check = DriverCheckService._attach_registration_number(driver_check, db)
        return driver_check

    @staticmethod
    def get_driver_check_by_hire_vehicle(hire_vehicle_provided_id: int, db: Session,request: Request = None):
        driver_check = (
            db.query(DriverCheck)
            .filter(DriverCheck.hire_vehicle_provided_id == hire_vehicle_provided_id)
            .first()
        )

        if not driver_check:
            raise HTTPException(status_code=404, detail="Driver Check not found for this hire vehicle")

        driver_check = DriverCheckService._attach_registration_number(driver_check, db)

        driver_check.interior_images = [
            DriverCheckImageOut.from_orm(img, request)
            for img in driver_check.images
            if img.image_type == DriverCheckImageType.INTERIOR
        ]

        driver_check.exterior_images = [
            DriverCheckImageOut.from_orm(img, request)
            for img in driver_check.images
            if img.image_type == DriverCheckImageType.EXTERIOR
        ]
        return driver_check

    @staticmethod
    def _image_base_dir():
        # absolute base dir for storage
        return os.path.abspath(os.path.join(os.getcwd(), "uploads", "driver-checks"))

    @staticmethod
    def _ensure_valid_image_type(image_type: str):
        image_type_lower = image_type.lower()
        if image_type_lower not in ("interior", "exterior"):
            raise HTTPException(status_code=400, detail="image_type must be 'interior' or 'exterior'")
        return image_type_lower

    @staticmethod
    def save_driver_check_images(driver_check_id: int, image_type: str, files: List[UploadFile], db: Session,
                                 current_user: int = None,tenant_id: int=None) -> List[DriverCheckImage]:
        """
        Saves uploaded files to filesystem and creates DriverCheckImage rows.
        Returns list of DriverCheckImage objects (not committed until DB commit within).
        """
        from libdata.models.tables import DriverCheckImage as DCI

        image_type = DriverCheckService._ensure_valid_image_type(image_type)

        # fetch driver_check for claim_id & hire_vehicle_provided_id
        driver_check = db.query(DriverCheck).filter(DriverCheck.id == driver_check_id).first()
        if not driver_check:
            raise HTTPException(status_code=404, detail="DriverCheck not found")

        claim_id = driver_check.claim_id
        hire_id = driver_check.hire_vehicle_provided_id

        base_dir = DriverCheckService._image_base_dir()
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        target_dir = os.path.join(base_dir, str(claim_id), str(hire_id), str(driver_check_id), image_type, ts)
        os.makedirs(target_dir, exist_ok=True)

        created = []
        for upfile in files:
            filename = upfile.filename or f"img_{len(created) + 1}.jpg"
            safe_filename = filename.replace("/", "_").replace("..", "_")  # simple sanitize
            path = os.path.join(target_dir, safe_filename)
            # write file
            with open(path, "wb") as out:
                out.write(upfile.file.read())

            rel_path = os.path.relpath(path, DriverCheckService._image_base_dir())
            stored_path = "/" + rel_path.replace("\\", "/")  # normalized path stored in DB
            img_row = DCI(
                driver_check_id=driver_check_id,
                image_type=DriverCheckImageType.INTERIOR if image_type == "interior" else DriverCheckImageType.EXTERIOR,
                file_path=stored_path,
                original_filename=safe_filename,
            )
            db.add(img_row)
            created.append(img_row)
            reference = build_case_reference(claim_id,db)
            history = HistoryActivities(
                claim_id=claim_id,
                file_name=f"The file named {safe_filename} has been saved for claim {reference}",
                file_path=stored_path,
                file_type=HistoryLogType.UPLOADED_DRIVER_CHECK_IMAGE,
                created_by=current_user,
                updated_by=current_user,
                tenant_id=tenant_id
            )
            db.add(history)

        db.commit()
        for r in created:
            db.refresh(r)
        return created

    @staticmethod
    def list_driver_check_images(driver_check_id: int, db: Session) -> List[DriverCheckImage]:
        imgs = db.query(DriverCheckImage).filter(DriverCheckImage.driver_check_id == driver_check_id).all()
        return imgs

    @staticmethod
    def delete_driver_check_image(image_id: int, db: Session):
        img = db.query(DriverCheckImage).filter(DriverCheckImage.id == image_id).first()
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")

        # delete file if exists (file_path is relative to the uploads/driver-checks dir)
        try:
            abs_path = os.path.join(
                DriverCheckService._image_base_dir(), (img.file_path or "").lstrip("/")
            )
            if os.path.exists(abs_path):
                os.remove(abs_path)
        except Exception:
            # log exception (not raising to avoid leaving DB inconsistent)
            pass

        db.delete(img)
        db.commit()
        return {"detail": "Image deleted"}

    @staticmethod
    def create_single_driver_check(payload, db: Session, current_user: int,tenant_id:int, exterior_files: List[UploadFile] = None,
                                   interior_files: List[UploadFile] = None,request: Request = None):
        hire_vehicle = db.query(HireVehicleProvided).filter(
            HireVehicleProvided.id == payload.hire_vehicle_provided_id,
            HireVehicleProvided.claim_id == payload.claim_id
        ).first()

        if not hire_vehicle:
            raise HTTPException(status_code=404, detail="Hire vehicle not found for this claim")

        if not hire_vehicle.hire_start_date:
            raise HTTPException(
                status_code=400,
                detail="Hire vehicle must have a hire_start_date before creating driver check"
            )

        DriverCheckService._validate_driver_check(payload)

        new_check = DriverCheck(
            **payload.dict(),
            created_by=current_user,
            updated_by=current_user,
        )
        db.add(new_check)
        db.flush()  # This gives us the ID without committing

        # Save interior images if any
        if interior_files:
            DriverCheckService.save_driver_check_images(
                driver_check_id=new_check.id,
                image_type="interior",
                files=interior_files,
                db=db,
                current_user=current_user,
                tenant_id=tenant_id
            )

        # Save exterior images if any
        if exterior_files:
            DriverCheckService.save_driver_check_images(
                driver_check_id=new_check.id,
                image_type="exterior",
                files=exterior_files,
                db=db,
                current_user=current_user,
                tenant_id=tenant_id
            )

        db.commit()
        db.refresh(new_check)

        # Add after db.refresh(new_check) and re-query
        new_check = db.query(DriverCheck).options(
            joinedload(DriverCheck.images)
        ).filter(DriverCheck.id == new_check.id).first()

        new_check = DriverCheckService._attach_registration_number(new_check, db)
        reference = build_case_reference(new_check.claim_id,db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=new_check.claim_id,
            file_name=f"The driver checkout detail has been created for claim {reference}",
            file_path="",
            file_type=HistoryLogType.CREATED_DRIVER_CHECK,
            user_id=current_user,
            tenant_id=tenant_id
        )

        new_check.interior_images = [
            DriverCheckImageOut.from_orm(img, request)
            for img in new_check.images
            if img.image_type == DriverCheckImageType.INTERIOR
        ]

        new_check.exterior_images = [
            DriverCheckImageOut.from_orm(img, request)
            for img in new_check.images
            if img.image_type == DriverCheckImageType.EXTERIOR
        ]

        return new_check

    FIELD_LABEL_MAP = {
        "currency": "Currency",
        "interior_clean_at_check_out": "Interior Clean (Check Out)",
        "interior_clean_at_check_in": "Interior Clean (Check In)",
        "interior_damage_at_check_in": "Interior Damage (Check In)",
        "describe_interior_damage": "Interior Damage Description",
        "exterior_clean_at_check_out": "Exterior Clean (Check Out)",
        "exterior_clean_at_check_in": "Exterior Clean (Check In)",
        "exterior_damage_at_check_in": "Exterior Damage (Check In)",
        "describe_exterior_damage": "Exterior Damage Description",
        "apply_petrol_checkout_charges": "Apply Petrol Charge",
        "petrol_checkout_charges": "Petrol Charge",
        "petrol_charges_note": "Petrol Charge Note",
        "apply_damage_charges": "Apply Damage Charge",
        "damage_charges": "Damage Charge",
        "damage_charges_paid_now": "Damage Paid Now",
        "damage_charges_note": "Damage Charge Note",
        "damage_charges_paid": "Damage Charges Paid",
        "valet_charges": "Valet Charges",
        "total_driver_checkout_charges": "Total Driver Checkout Charges",
    }

    @staticmethod
    def update_driver_check_by_hire_vehicle_image(
            hire_vehicle_provided_id: int,
            payload,
            db: Session,
            current_user: int,
            tenant_id: int,
            interior_files: List[UploadFile] = None,
            exterior_files: List[UploadFile] = None,
            request: Request = None
    ):
        driver_check = db.query(DriverCheck).filter(
            DriverCheck.hire_vehicle_provided_id == hire_vehicle_provided_id
        ).first()

        if not driver_check:
            raise HTTPException(status_code=404, detail="Driver Check not found for this hire vehicle")

        changed_fields = []
        data = payload.dict(exclude_unset=True)

        # --- Detect and update changed fields ---
        for key, new_val in data.items():
            old_val = getattr(driver_check, key)
            if old_val != new_val:
                changed_fields.append(key)
                setattr(driver_check, key, new_val)

        driver_check.updated_by = current_user
        db.add(driver_check)
        db.flush()

        claim_id = driver_check.claim_id

        # -----------------------------
        # Interior Image Replacement
        # -----------------------------
        if interior_files:
            # delete old
            db.query(DriverCheckImage).filter(
                DriverCheckImage.driver_check_id == driver_check.id,
                DriverCheckImage.image_type == DriverCheckImageType.INTERIOR
            ).delete(synchronize_session=False)
            db.flush()

            # save new
            DriverCheckService.save_driver_check_images(
                driver_check_id=driver_check.id,
                image_type="interior",
                files=interior_files,
                db=db,
                current_user=current_user,
                tenant_id=tenant_id
            )

            # add history "interior_images"
            changed_fields.append("interior_images")

        # -----------------------------
        # Exterior Image Replacement
        # -----------------------------
        if exterior_files:
            # delete old
            db.query(DriverCheckImage).filter(
                DriverCheckImage.driver_check_id == driver_check.id,
                DriverCheckImage.image_type == DriverCheckImageType.EXTERIOR
            ).delete(synchronize_session=False)
            db.flush()

            # save new
            DriverCheckService.save_driver_check_images(
                driver_check_id=driver_check.id,
                image_type="exterior",
                files=exterior_files,
                db=db,
                current_user=current_user,
                tenant_id=tenant_id
            )

            # add history "exterior_images"
            changed_fields.append("exterior_images")

        db.commit()
        db.refresh(driver_check)

        if changed_fields:
            readable = [
                DriverCheckService.FIELD_LABEL_MAP.get(field, field)
                for field in changed_fields
            ]
            reference = build_case_reference(claim_id,db)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim_id,
                file_name=f"The driver checkout detail has been updated for claim {reference}",
                file_path=", ".join(readable),
                file_type=HistoryLogType.UPDATED_DRIVER_CHECK,
                user_id=current_user,
                tenant_id=tenant_id
            )
        # Re-fetch with images
        driver_check = db.query(DriverCheck).options(joinedload(DriverCheck.images)).filter(
            DriverCheck.id == driver_check.id
        ).first()

        driver_check = DriverCheckService._attach_registration_number(driver_check, db)

        driver_check.interior_images = [
            DriverCheckImageOut.from_orm(img, request)
            for img in driver_check.images
            if img.image_type == DriverCheckImageType.INTERIOR
        ]

        driver_check.exterior_images = [
            DriverCheckImageOut.from_orm(img, request)
            for img in driver_check.images
            if img.image_type == DriverCheckImageType.EXTERIOR
        ]

        return driver_check

    @staticmethod
    def save_checkout_json(
        payload: DriverCheckCreate,
        db: Session,
        current_user: int,
        tenant_id: int = None,
        interior_files: List[UploadFile] = None,
        exterior_files: List[UploadFile] = None,
    ) -> DriverCheck:
        """Create or update a DriverCheck record. Used by the checkout form.

        Optionally attaches interior/exterior photos. Images are written to the
        local filesystem (see save_driver_check_images), so photo upload keeps
        working even when external services (S3/DNS) are unavailable.
        """
        existing = db.query(DriverCheck).filter(
            DriverCheck.hire_vehicle_provided_id == payload.hire_vehicle_provided_id
        ).first()

        if existing:
            for key, value in payload.dict(exclude={"claim_id", "hire_vehicle_provided_id"}).items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_by = current_user
            db.commit()
            db.refresh(existing)
            check = existing
        else:
            check = DriverCheck(**payload.dict(), created_by=current_user, updated_by=current_user)
            db.add(check)
            db.commit()
            db.refresh(check)

        # Valet charge auto-rule (check-in cleanliness truth table): £30 if the
        # interior OR exterior is NOT clean at check-in, otherwise £0. This is
        # enforced server-side so the stored value (and the confirmation email)
        # always matches the rule regardless of what the client sent.
        interior_clean = bool(getattr(check, "interior_clean_at_check_in", False))
        exterior_clean = bool(getattr(check, "exterior_clean_at_check_in", False))
        new_valet = 0 if (interior_clean and exterior_clean) else 30
        petrol = (
            float(check.petrol_checkout_charges or 0)
            if getattr(check, "apply_petrol_checkout_charges", False)
            else 0
        )
        damage = (
            float(check.damage_charges or 0)
            if getattr(check, "apply_damage_charges", False)
            else 0
        )
        check.valet_charges = new_valet
        check.total_driver_checkout_charges = new_valet + petrol + damage
        check.updated_by = current_user
        db.commit()
        db.refresh(check)

        if interior_files:
            DriverCheckService.save_driver_check_images(
                driver_check_id=check.id,
                image_type="interior",
                files=interior_files,
                db=db,
                current_user=current_user,
                tenant_id=tenant_id,
            )
        if exterior_files:
            DriverCheckService.save_driver_check_images(
                driver_check_id=check.id,
                image_type="exterior",
                files=exterior_files,
                db=db,
                current_user=current_user,
                tenant_id=tenant_id,
            )

        db.refresh(check)
        return check

    @staticmethod
    def send_checkout_email(claim_id: int, hire_vehicle_provided_id: int, db: Session):
        """Send checkout confirmation email to the client after driver check-in."""
        hvp = db.query(HireVehicleProvided).filter(HireVehicleProvided.id == hire_vehicle_provided_id).first()
        if not hvp:
            raise HTTPException(404, "Hire vehicle not found")

        driver_check = db.query(DriverCheck).filter(
            DriverCheck.hire_vehicle_provided_id == hire_vehicle_provided_id
        ).first()
        if not driver_check:
            raise HTTPException(404, "Driver check not found for this hire vehicle")

        # A claim has multiple ClientDetail rows (CLIENT, DRIVER, ...). Filter to the
        # CLIENT so the name/email belong to the actual client, not the driver etc.
        client = (
            db.query(ClientDetail)
            .filter(ClientDetail.claim_id == claim_id, ClientDetail.role == "CLIENT")
            .first()
        )
        if not client:
            client = db.query(ClientDetail).filter(ClientDetail.claim_id == claim_id).first()
        address = db.query(Address).filter(Address.id == client.address_id).first() if (client and client.address_id) else None
        referrer = db.query(Referrer).filter(Referrer.claim_id == claim_id).first()
        vehicle = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()

        client_email = address.email if (address and address.email) else None

        case_ref = build_case_reference(claim_id, db)
        client_name = f"{client.first_name or ''} {client.surname or ''}".strip() if client else "N/A"
        referrer_name = referrer.company_name if referrer else "N/A"
        hire_make_model = f"{hvp.make or ''} {hvp.model or ''}".strip() or "N/A"
        hire_reg = hvp.hire_vehicle_registration or "N/A"
        client_vehicle = vehicle.registration if vehicle else "N/A"

        def yn(val: bool) -> str:
            return "Yes" if val else "No"

        def money(val) -> str:
            try:
                return f"{float(val):.2f}"
            except Exception:
                return "0.00"

        def row(label: str, value: str) -> str:
            return f"""
            <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;">
              <div style="width:200px;font-size:11px;color:#334155;font-weight:400;">{label}</div>
              <div style="flex:1;font-size:11px;color:#334155;font-weight:600;">{value}</div>
            </div>"""

        def divider() -> str:
            return '<div style="height:1px;background:#e2e8f0;width:100%;margin:2px 0;"></div>'

        def card(content: str) -> str:
            return f"""
            <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;
                        max-width:384px;margin:0 auto 16px auto;">
              {content}
            </div>"""

        def section_title(title: str) -> str:
            return f'<div style="font-size:13px;font-weight:700;padding:8px 0 6px;">{title}</div>'

        def _photo_thumbs_and_attachments(images):
            """Build inline <img> thumbnails for the given DriverCheckImage rows and
            collect their base64 content so they can be attached inline to the email."""
            thumbs, atts = "", []
            for img in images:
                disk_path = os.path.join(
                    DriverCheckService._image_base_dir(), (img.file_path or "").lstrip("/")
                )
                try:
                    with open(disk_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                except Exception as exc:
                    logger.warning(f"checkout email: could not read image {disk_path}: {exc}")
                    continue
                cid = f"dcimg{img.id}"
                name = (img.original_filename or "").lower()
                ctype = "image/png" if name.endswith(".png") else "image/jpeg"
                atts.append({"cid": cid, "content_bytes": b64, "content_type": ctype})
                thumbs += (
                    f'<img src="cid:{cid}" width="72" height="72" '
                    f'style="width:72px;height:72px;object-fit:cover;border-radius:6px;'
                    f'margin:8px 8px 0 0;border:1px solid #e2e8f0;" />'
                )
            block = f'<div style="margin-top:6px;">{thumbs}</div>' if thumbs else ""
            return block, atts

        all_images = list(getattr(driver_check, "images", []) or [])
        interior_block, interior_atts = _photo_thumbs_and_attachments(
            [i for i in all_images if i.image_type == DriverCheckImageType.INTERIOR]
        )
        exterior_block, exterior_atts = _photo_thumbs_and_attachments(
            [i for i in all_images if i.image_type == DriverCheckImageType.EXTERIOR]
        )
        photo_attachments = interior_atts + exterior_atts

        html = f"""
        <div style="font-family:Arial,sans-serif;background:#fff;padding:30px 20px;color:#334155;max-width:640px;margin:0 auto;">
          <div style="text-align:center;margin-bottom:24px;">
            <img src="cid:companylogo" alt="Logo" width="48" style="width:48px;height:auto;">
          </div>

          {card(
            row("Case", case_ref) +
            divider() +
            row("Client Name", client_name) +
            divider() +
            row("Referrer", referrer_name) +
            divider() +
            row("Hire Vehicle Make/Model", hire_make_model) +
            divider() +
            row("Hire Vehicle Registration", hire_reg) +
            divider() +
            row("Vehicle", client_vehicle)
          )}

          <div style="max-width:384px;margin:0 auto 16px auto;font-size:13px;line-height:1.6;">
            Please note that we have checked in the hire vehicle stated above and have noted
            any damages and the cleanliness of the vehicle below for your information.
          </div>

          {card(
            section_title("Interior (Inside)") +
            row("Interior Clean at Checkout?", yn(driver_check.interior_clean_at_check_out)) +
            divider() +
            row("Interior Clean at Check In?", yn(driver_check.interior_clean_at_check_in)) +
            (divider() + row("Description", driver_check.describe_interior_damage or "") if driver_check.interior_damage_at_check_in else "") +
            interior_block
          )}

          {card(
            section_title("Exterior (Outside)") +
            row("Exterior Clean at Checkout?", yn(driver_check.exterior_clean_at_check_out)) +
            divider() +
            row("Exterior Clean at Check In?", yn(driver_check.exterior_clean_at_check_in)) +
            (divider() + row("Description", driver_check.describe_exterior_damage or "") if driver_check.exterior_damage_at_check_in else "") +
            exterior_block
          )}

          <div style="max-width:384px;margin:0 auto 16px auto;font-size:13px;line-height:1.6;">
            Please review the above prior to authorising the driver to be paid.
          </div>

          {card(
            row("Valet Charges", f"£{money(driver_check.valet_charges)}") +
            divider() +
            row("Petrol Charges", f"£{money(driver_check.petrol_checkout_charges)}") +
            divider() +
            row("Vehicle Damage Charges", f"£{money(driver_check.damage_charges)}")
          )}

          <div style="max-width:580px;height:1px;background:#e2e8f0;margin:20px auto;"></div>
          <div style="text-align:center;">
            <p style="font-size:12px;font-weight:600;margin:0;">Kind regards,</p>
            <p style="font-size:14px;font-weight:600;margin:4px 0;">Nationwide Assist<br>IT / Systems Team</p>
          </div>
        </div>
        """

        # Subject: switchover notice. Prefix with "CHARGES" only when the valet
        # charge applies per the check-in cleanliness truth table (£30).
        def _f(val) -> float:
            try:
                return float(val or 0)
            except Exception:
                return 0.0

        charges_apply = _f(driver_check.valet_charges) > 0
        base_subject = "Switchover Inform Claims Operations Of Any Hire Vehicle Damages"
        subject = (
            f"CHARGES {base_subject} – {case_ref}"
            if charges_apply
            else f"{base_subject} – {case_ref}"
        )

        # Recipients: the client (if we have their email) plus a copy to the
        # connected Outlook mailbox so the team always sees the confirmation.
        # Only skip if there is genuinely no one to send to (no hard 400).
        copy_to = (
            os.getenv("HIRE_INSTRUCTION_COPY_EMAIL", "")
            or os.getenv("MS_GRAPH_MAILBOX", "")
            or os.getenv("OUTLOOK_MAILBOX", "")
        )
        recipients = [e for e in [client_email, copy_to] if e and "@" in e]
        if not recipients:
            logger.warning(f"checkout email skipped for claim {claim_id}: no recipients")
            return {"status": "skipped", "detail": "No client email and no copy recipient configured"}

        # Prefer Microsoft Graph (delivered from a real Outlook mailbox);
        # fall back to SendGrid only if Graph isn't available or fails.
        if GraphEmailService.is_configured():
            result = GraphEmailService.send_mail(
                recipients, subject, html, inline_images=photo_attachments
            )
            if result is not None:
                return {"status": "sent", "via": "graph", "recipients": recipients}
            logger.warning("Graph send failed for checkout email; falling back to SendGrid")

        message = Mail(
            from_email="No-Reply <noreplynationwideassist@yopmail.com>",
            to_emails=recipients,
            subject=subject,
            html_content=html,
        )
        if _LOGO_ENCODED:
            message.add_attachment(Attachment(
                FileContent(_LOGO_ENCODED), FileName("logo.png"),
                FileType("image/png"), Disposition("inline"), ContentId("companylogo"),
            ))
        for att in photo_attachments:
            message.add_attachment(Attachment(
                FileContent(att["content_bytes"]), FileName(f"{att['cid']}.jpg"),
                FileType(att["content_type"]), Disposition("inline"), ContentId(att["cid"]),
            ))

        api_key = os.getenv("SENDGRID_API_KEY")
        if not api_key:
            return {"status": "skipped", "detail": "SendGrid API key not configured"}

        try:
            sg = SendGridAPIClient(api_key)
            response = sg.send(message)
            return {"status": "sent", "via": "sendgrid", "sendgrid_status": response.status_code}
        except Exception as e:
            logger.warning(f"checkout email send failed for claim {claim_id}: {e}")
            return {"status": "failed", "detail": str(e)}
