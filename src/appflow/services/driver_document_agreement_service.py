from datetime import datetime
from typing import Dict, Set

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from libdata.models.tables import DriverDocumentAgreement
from appflow.models.driver_documents_agreements import DriverDocumentAgreementCreate
from appflow.services.history_activity_service import HistoryActivityService
from appflow.services.s3_service import S3Service
from libdata.enums import HistoryLogType
from appflow.utils import build_case_reference
from libdata.models.tables import CaseDocument

class DriverDocumentAgreementService:
    """Service layer for Driver Documents & Agreements"""

    DATE_FIELDS: Set[str] = {
        "driver_license_received_on",
        "license_checks_completed_on",
        "proof_of_address_1_received_on",
        "proof_of_address_2_received_on",
        "pre_hire_bank_statement_received_on",
        "post_hire_bank_statement_received_on",
        "taxi_badge_received_on",
        "v5_received_on",
        "mot_certificate_received_on",
        "insurance_certificate_received_on",
        "suspension_notice_received_on",
        "suspension_uplift_received_on",
        "signed_cha_received_on",
        "signed_mitigation_received_on",
        "arf_received_on",
        "signed_cil_agreement_received_on",
    }

    FILE_URL_FIELDS: Set[str] = {
        "driver_license_file_url",
        "license_checks_completed_file_url",
        "proof_of_address_1_file_url",
        "proof_of_address_2_file_url",
        "pre_hire_bank_statement_file_url",
        "post_hire_bank_statement_file_url",
        "taxi_badge_file_url",
        "v5_file_url",
        "mot_certificate_file_url",
        "insurance_certificate_file_url",
        "suspension_notice_file_url",
        "suspension_uplift_file_url",
        "signed_cha_file_url",
        "signed_mitigation_file_url",
        "arf_file_url",
        "signed_cil_agreement_file_url",
    }

    FIELD_TO_FILE_MAP = {
        "driver_license_received_on": "driver_license_file_url",
        "license_checks_completed_on": "license_checks_completed_file_url",
        "proof_of_address_1_received_on": "proof_of_address_1_file_url",
        "proof_of_address_2_received_on": "proof_of_address_2_file_url",
        "pre_hire_bank_statement_received_on": "pre_hire_bank_statement_file_url",
        "post_hire_bank_statement_received_on": "post_hire_bank_statement_file_url",
        "taxi_badge_received_on": "taxi_badge_file_url",
        "v5_received_on": "v5_file_url",
        "mot_certificate_received_on": "mot_certificate_file_url",
        "insurance_certificate_received_on": "insurance_certificate_file_url",
        "suspension_notice_received_on": "suspension_notice_file_url",
        "suspension_uplift_received_on": "suspension_uplift_file_url",
        "signed_cha_received_on": "signed_cha_file_url",
        "signed_mitigation_received_on": "signed_mitigation_file_url",
        "arf_received_on": "arf_file_url",
        "signed_cil_agreement_received_on": "signed_cil_agreement_file_url",
    }

    FIELD_LABEL_MAP = {
        "driver_license_received_on": "Driver License Received On",
        "driver_license_file_url": "Driver License File",
        "license_checks_completed_on": "License Checks Completed On",
        "license_checks_completed_file_url": "License Checks File",
        "proof_of_address_1_received_on": "Proof of Address 1 Received On",
        "proof_of_address_1_file_url": "Proof of Address 1 File",
        "proof_of_address_2_received_on": "Proof of Address 2 Received On",
        "proof_of_address_2_file_url": "Proof of Address 2 File",
        "pre_hire_bank_statement_received_on": "Bank Statement Received On (Pre-hire)",
        "pre_hire_bank_statement_file_url": "Bank Statement File (Pre-hire)",
        "post_hire_bank_statement_received_on": "Bank Statement Received On (Post-hire)",
        "post_hire_bank_statement_file_url": "Bank Statement File (Post-hire)",
        "taxi_badge_received_on": "Taxi Badge Received On",
        "taxi_badge_file_url": "Taxi Badge File",
        "v5_received_on": "V5 Received On",
        "v5_file_url": "V5 File",
        "mot_certificate_received_on": "MOT Certificate Received On",
        "mot_certificate_file_url": "MOT Certificate File",
        "insurance_certificate_received_on": "Insurance Certificate Received On",
        "insurance_certificate_file_url": "Insurance Certificate File",
        "suspension_notice_received_on": "Suspension Notice Received On",
        "suspension_notice_file_url": "Suspension Notice File",
        "suspension_uplift_received_on": "Suspension UPLIFT Received On",
        "suspension_uplift_file_url": "Suspension UPLIFT File",
        "signed_cha_received_on": "Signed CHA Received On",
        "signed_cha_file_url": "Signed CHA File",
        "signed_mitigation_received_on": "Signed Mitigation Received On",
        "signed_mitigation_file_url": "Signed Mitigation File",
        "arf_received_on": "ARF Received On",
        "arf_file_url": "ARF File",
        "signed_cil_agreement_received_on": "Signed CIL Agreement Received On",
        "signed_cil_agreement_file_url": "Signed CIL Agreement File",
    }

    @staticmethod
    def create(payload: DriverDocumentAgreementCreate, db: Session, user_id: int, tenant_id: int):
        existing = (
            db.query(DriverDocumentAgreement)
            .filter(DriverDocumentAgreement.claim_id == payload.claim_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Driver document record already exists for this claim.",
            )

        new_record = DriverDocumentAgreement(
            **payload.model_dump(),
            created_by=user_id,
            created_at=datetime.utcnow(),
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        reference = build_case_reference(payload.claim_id, db)
        HistoryActivityService.create_activity(
            db=db,
            claim_id=payload.claim_id,
            file_name=f"The driver document and agreement has been created for claim {reference}",
            file_path="",
            file_type=HistoryLogType.CREATED_DRIVER_AGREEMENT,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        return new_record

    @staticmethod
    def get_by_claim(claim_id: int, db: Session):
        record = (
            db.query(DriverDocumentAgreement)
            .filter(
                DriverDocumentAgreement.claim_id == claim_id,
                DriverDocumentAgreement.is_deleted == False,
            )
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver document record not found for this claim.",
            )
        return record

    @staticmethod
    def update_by_claim_id(claim_id: int, payload, db: Session, user_id: int, tenant_id: int):
        record = (
            db.query(DriverDocumentAgreement)
            .filter(DriverDocumentAgreement.claim_id == claim_id)
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver document record not found for this claim.",
            )

        payload_dict = payload.model_dump(exclude_unset=True)
        changed_fields = []

        for field, new_value in payload_dict.items():
            if not hasattr(record, field):
                continue

            old_value = getattr(record, field)

            if isinstance(old_value, datetime) and isinstance(new_value, datetime):
                if old_value.date() != new_value.date():
                    setattr(record, field, new_value)
                    changed_fields.append(
                        DriverDocumentAgreementService.FIELD_LABEL_MAP.get(field, field)
                    )
            else:
                if old_value != new_value:
                    setattr(record, field, new_value)
                    changed_fields.append(
                        DriverDocumentAgreementService.FIELD_LABEL_MAP.get(field, field)
                    )

        record.updated_by = user_id
        record.updated_at = datetime.utcnow()

        db.add(record)
        db.commit()
        db.refresh(record)

        reference = build_case_reference(claim_id, db)
        if changed_fields:
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim_id,
                file_name=f"The driver document and agreement has been updated for claim {reference}",
                file_path=", ".join(changed_fields),
                file_type=HistoryLogType.UPDATED_DRIVER_AGREEMENT,
                user_id=user_id,
                tenant_id=tenant_id,
            )

        return record

    @staticmethod
    def upload_document_for_claim(
        claim_id: int,
        field_name: str,
        file: UploadFile,
        db: Session,
        user_id: int,
        tenant_id: int,
    ):
        record = (
            db.query(DriverDocumentAgreement)
            .filter(DriverDocumentAgreement.claim_id == claim_id)
            .first()
        )

        if not record:
            record = DriverDocumentAgreement(
                claim_id=claim_id,
                created_by=user_id,
                created_at=datetime.utcnow(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)

        if field_name not in DriverDocumentAgreementService.FIELD_TO_FILE_MAP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid field_name: {field_name}",
            )

        file_url_field = DriverDocumentAgreementService.FIELD_TO_FILE_MAP.get(field_name)

        if not file_url_field:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No file URL field configured for: {field_name}",
            )

        s3_service = S3Service()
        upload_result = s3_service.upload_driver_document(
            file=file,
            claim_id=claim_id,
            field_name=field_name,
        )

        file_url = upload_result["file_url"]
        s3_key = upload_result["s3_key"]

        new_doc = CaseDocument(
            claim_id=claim_id,
            file_name=file.filename,
            original_filename=file.filename,
            file_extension=file.filename.split(".")[-1],
            content_type=file.content_type,
            category="User Uploads",  # or "Driver Documents"
            tag="Driver Agreement",
            source_type="driver_document",
            

            s3_key=s3_key,
            file_url=file_url,

            version=1,
            is_latest=True,

            created_by=user_id,
            updated_by=user_id,
            tenant_id=tenant_id,
        )

        db.add(new_doc)
        db.commit()

        setattr(record, file_url_field, file_url)

        if getattr(record, field_name) is None:
            setattr(record, field_name, datetime.utcnow())

        record.updated_by = user_id
        record.updated_at = datetime.utcnow()

        db.add(record)
        db.commit()
        db.refresh(record)

        reference = build_case_reference(claim_id, db)
        clean_file_name = file.filename.split("/")[-1].split("\\")[-1]

        HistoryActivityService.create_activity(
            db=db,
            claim_id=claim_id,
            file_name=clean_file_name,
            file_path=file_url,
            file_type=HistoryLogType.HISTORYUPLOAD,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        return {
            "field_name": field_name,
            "file_name": clean_file_name,
            "file_url": file_url,
            "uploaded_at": record.updated_at or datetime.utcnow(),
        }

    @staticmethod
    def deactivate_by_claim_id(claim_id: int, db: Session, user_id: int):
        record = (
            db.query(DriverDocumentAgreement)
            .filter(
                DriverDocumentAgreement.claim_id == claim_id,
                DriverDocumentAgreement.is_active == True,
            )
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active driver document record not found for this claim.",
            )

        record.is_active = False
        record.is_deleted = True
        record.updated_by = user_id
        record.updated_at = datetime.utcnow()

        db.add(record)
        db.commit()
        return {"message": "Driver document record deactivated successfully."}