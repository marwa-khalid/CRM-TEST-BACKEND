import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from appflow.services.roboflow_service import roboflow_service
from appflow.services.ai_report_pdf_service import AIReportPDFService
from appflow.services.s3_service import S3Service
from appflow.utils import build_case_reference, handler_name_for_user
from libdata.enums import HistoryLogType, PersonRoleEnum
from libdata.models.tables import (
    CaseDocument,
    CaseDocumentAuditLog,
    ClientDetail,
    HistoryActivities,
    ThirdPartyVehicle,
    VehicleDamageAIReport,
    VehicleDetail,
)


class VehicleDamageAIReportService:

    # -----------------------------------------------------------------
    # GET latest
    # -----------------------------------------------------------------
    @staticmethod
    def get_latest_by_claim(claim_id: int, db: Session) -> VehicleDamageAIReport:
        report = (
            db.query(VehicleDamageAIReport)
            .options(joinedload(VehicleDamageAIReport.images))
            .filter(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.is_latest == True,
                VehicleDamageAIReport.is_deleted == False,
            )
            .order_by(VehicleDamageAIReport.version.desc(), VehicleDamageAIReport.id.desc())
            .first()
        )

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No AI report found for this claim.",
            )

        s3_service = S3Service()

        # refresh per-image presigned URLs
        if report.report_payload and report.report_payload.get("images"):
            refreshed_images = []
            for item in report.report_payload["images"]:
                refreshed_item = dict(item)
                if item.get("original_image_s3_key"):
                    refreshed_item["original_image_url"] = s3_service.generate_presigned_download_url(
                        item["original_image_s3_key"]
                    )
                if item.get("annotated_image_s3_key"):
                    refreshed_item["annotated_image_url"] = s3_service.generate_presigned_download_url(
                        item["annotated_image_s3_key"]
                    )
                refreshed_images.append(refreshed_item)
            report.report_payload["images"] = refreshed_images

        # refresh the consolidated report PDF presigned URL too
        if report.report_payload and report.report_payload.get("report_pdf_s3_key"):
            fresh_pdf_url = s3_service.generate_presigned_download_url(
                report.report_payload["report_pdf_s3_key"]
            )
            report.report_payload["report_pdf_url"] = fresh_pdf_url
            report.pdf_report_url = fresh_pdf_url

        return report

    # -----------------------------------------------------------------
    # ANALYZE + STORE  (single consolidated PDF)
    # -----------------------------------------------------------------
    @staticmethod
    async def analyze_and_store(
        claim_id: int,
        assessment_type: str,
        images: list,
        db: Session,
        user_id: int,
        tenant_id: int,
        existing_images: Optional[list] = None,
        third_party_images: Optional[list] = None,
    ):
        images = images or []
        third_party_images = third_party_images or []
        if not images and not third_party_images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one image is required to analyze.",
            )

        s3_service = S3Service()

        # ----- 1. Get or create the latest report row -----
        latest_report = (
            db.query(VehicleDamageAIReport)
            .filter(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.is_latest == True,
                VehicleDamageAIReport.is_deleted == False,
            )
            .order_by(VehicleDamageAIReport.version.desc(), VehicleDamageAIReport.id.desc())
            .first()
        )

        if not latest_report:
            latest_report = VehicleDamageAIReport(
                claim_id=claim_id,
                version=1,
                is_latest=True,
                is_deleted=False,
                created_by=user_id,
                updated_by=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(latest_report)
            db.commit()
            db.refresh(latest_report)

        # ----- 2. Process each image: detect, annotate, upload -----
        processed_images = []      # list passed to PDF builder (gallery)
        restored_images = []       # list persisted to report_payload (with S3 keys)
        all_predictions = []       # flat list of every prediction across images

        async def _process_image(image, index, vehicle_type):
            content = await image.read()
            original_filename = image.filename or f"image_{index}.jpg"

            # upload original
            original_upload = s3_service.upload_claim_image_bytes(
                image_bytes=content,
                claim_id=claim_id,
                filename=original_filename,
                category="ai-images",
            )

            # write temp file for annotation
            fd, temp_path = tempfile.mkstemp(suffix=Path(original_filename).suffix or ".jpg")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(content)

                # reset UploadFile pointer for roboflow
                image.file.seek(0)

                result = await roboflow_service.detect_car_damage(
                    image,
                    include_annotated_image=False,
                    image_index=index,
                )
                predictions = result.get("predictions", []) or []

                # stamp image_index + vehicle_type so the slider can group/switch
                for p in predictions:
                    p["image_index"] = index
                    p["vehicle_type"] = vehicle_type
                    all_predictions.append(p)

                # build + upload annotated image
                annotated_bytes = roboflow_service.create_image_bytes(temp_path, predictions)
                annotated_upload = s3_service.upload_ai_image_bytes(
                    image_bytes=annotated_bytes,
                    claim_id=claim_id,
                    filename=f"annotated_{original_filename}",
                    category="ai-annotated-images",
                )

                original_url = s3_service.generate_presigned_download_url(original_upload["s3_key"])
                annotated_url = s3_service.generate_presigned_download_url(annotated_upload["s3_key"])

                # for the PDF (needs URLs only, no DB ids)
                processed_images.append({
                    "image_index": index,
                    "original_filename": original_filename,
                    "original_image_url": original_url,
                    "annotated_image_url": annotated_url,
                    "predictions": predictions,
                    "vehicle_type": vehicle_type,
                })

                # for persistence (keep S3 keys so URLs can be refreshed later)
                restored_images.append({
                    "image_index": index,
                    "original_filename": original_filename,
                    "original_image_s3_key": original_upload["s3_key"],
                    "original_image_url": original_url,
                    "annotated_image_s3_key": annotated_upload["s3_key"],
                    "annotated_image_url": annotated_url,
                    "predictions": predictions,
                    "vehicle_type": vehicle_type,
                })

            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        # When the sole assessment is the third party, the single `images` set is
        # the third party's; otherwise `images` is the client's and the dedicated
        # `third_party_images` set (Both) is the third party's. image_index is
        # global across both sets so predictions still group per image.
        primary_type = "third_party" if assessment_type == "Third Party Vehicle Only" else "client"
        running_index = 0
        for image in images:
            await _process_image(image, running_index, primary_type)
            running_index += 1
        for image in third_party_images:
            await _process_image(image, running_index, "third_party")
            running_index += 1

        # ----- 2b. Merge already-analyzed images (from the current report) in
        # front of the freshly-analyzed ones, so we rebuild ONE consolidated
        # report WITHOUT re-running OCR on the images already processed. -----
        if existing_images:
            shift = len(existing_images)
            for img in processed_images:
                img["image_index"] = (img.get("image_index") or 0) + shift
            for img in restored_images:
                img["image_index"] = (img.get("image_index") or 0) + shift
            for p in all_predictions:
                p["image_index"] = (p.get("image_index") or 0) + shift

            existing_processed, existing_restored, existing_predictions = [], [], []
            for i, img in enumerate(existing_images):
                o_key = img.get("original_image_s3_key")
                a_key = img.get("annotated_image_s3_key")
                o_url = (
                    s3_service.generate_presigned_download_url(o_key)
                    if o_key else (img.get("original_image_url") or "")
                )
                a_url = (
                    s3_service.generate_presigned_download_url(a_key)
                    if a_key else (img.get("annotated_image_url") or "")
                )
                filename = img.get("original_filename") or f"image_{i}.jpg"
                vtype = img.get("vehicle_type") or "client"
                norm_preds = [{**p, "image_index": i, "vehicle_type": p.get("vehicle_type") or vtype} for p in (img.get("predictions") or [])]
                existing_predictions.extend(norm_preds)
                existing_processed.append({
                    "image_index": i,
                    "original_filename": filename,
                    "original_image_url": o_url,
                    "annotated_image_url": a_url,
                    "predictions": norm_preds,
                    "vehicle_type": vtype,
                })
                existing_restored.append({
                    "image_index": i,
                    "original_filename": filename,
                    "original_image_s3_key": o_key,
                    "original_image_url": o_url,
                    "annotated_image_s3_key": a_key,
                    "annotated_image_url": a_url,
                    "predictions": norm_preds,
                    "vehicle_type": vtype,
                })

            processed_images = existing_processed + processed_images
            restored_images = existing_restored + restored_images
            all_predictions = existing_predictions + all_predictions

        # ----- 3. Build ONE consolidated PDF after processing everything -----
        client_name = VehicleDamageAIReportService._get_client_name(claim_id, db)
        # The AI report is generated by the logged-in claim handler — attribute
        # the audit trail / "Uploaded By" to their name, not the client.
        handler_name = handler_name_for_user(db, user_id) or "Claim Handler"
        case_reference = build_case_reference(claim_id, db)
        report_id = AIReportPDFService.generate_report_id()
        generated_at = datetime.utcnow()
        generated_at_iso = generated_at.isoformat()

        audit_trail = [{
            "doneBy": handler_name,
            "action": "Generated Collective AI Report",
            "timestamp": generated_at_iso,
        }]

        # Vehicle cards (client + third party) for the report header.
        client_vehicle = None
        third_party_vehicle = None
        cv = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
        if cv:
            client_vehicle = {
                "registration": getattr(cv, "registration", None),
                "make": getattr(cv, "make", None),
                "model": getattr(cv, "model", None),
                "year": getattr(cv, "year", None) or getattr(cv, "manufacture_year", None),
                "color": getattr(cv, "color", None) or getattr(cv, "colour", None),
            }
            # Third party make/model/reg come from the third party vehicle area
            # on the vehicle details screen; if more than one, take the latest.
            tpv = (
                db.query(ThirdPartyVehicle)
                .filter(
                    ThirdPartyVehicle.client_vehicle_id == cv.id,
                    ThirdPartyVehicle.is_deleted == False,
                )
                .order_by(
                    ThirdPartyVehicle.created_at.desc(),
                    ThirdPartyVehicle.id.desc(),
                )
                .first()
            )
            if tpv:
                third_party_vehicle = {
                    "registration": getattr(tpv, "registration", None),
                    "make": getattr(tpv, "make", None),
                    "model": getattr(tpv, "model", None),
                    "year": getattr(tpv, "year", None),
                    "color": getattr(tpv, "color", None) or getattr(tpv, "colour", None),
                }

        pdf_bytes = AIReportPDFService.build_collective_pdf_bytes(
            claim_reference=case_reference,
            images=processed_images,
            predictions=all_predictions,
            report_id=report_id,
            generated_at=generated_at_iso,
            uploaded_by=handler_name,
            source_name="Claim Portal",
            assessment_type=assessment_type,
            audit_trail=audit_trail,
            client_vehicle=client_vehicle,
            third_party_vehicle=third_party_vehicle,
        )

        # ----- 4. Upload the single PDF to S3 -----
        pdf_upload = s3_service.upload_ai_report_pdf_bytes(
            pdf_bytes=pdf_bytes,
            claim_id=claim_id,
            file_name=f"{report_id}_AI_Damage_Report.pdf",
        )
        pdf_presigned_url = s3_service.generate_presigned_download_url(pdf_upload["s3_key"])

        # ----- 5. Create ONE case document for this consolidated report -----
        prediction_count = len(all_predictions)
        high_severity_count = len(
            [p for p in all_predictions if (p.get("severity") or "").lower() == "high"]
        )

        case_document = VehicleDamageAIReportService._create_case_document_for_ai_report(
            db=db,
            claim_id=claim_id,
            tenant_id=tenant_id,
            user_id=user_id,
            client_name=client_name,
            image_name=f"{len(processed_images)} image(s)",
            assessment_type=assessment_type,
            prediction_count=prediction_count,
            high_severity_count=high_severity_count,
            report_id=latest_report.id,
            generated_at=generated_at,
            pdf_upload={
                "s3_key": pdf_upload["s3_key"],
                "file_url": pdf_presigned_url,
            },
            pdf_bytes=pdf_bytes,
        )

        # ----- 6. Create ONE history activity entry -----
        history_payload = VehicleDamageAIReportService._build_ai_history_payload(
            client_name=client_name,
            image_name=f"{len(processed_images)} image(s)",
            assessment_type=assessment_type,
            prediction_count=prediction_count,
            high_severity_count=high_severity_count,
            generated_at=generated_at_iso,
            report_id=latest_report.id,
            case_document_id=case_document.id,
        )
        VehicleDamageAIReportService._create_ai_report_history(
            db=db,
            claim_id=claim_id,
            tenant_id=tenant_id,
            user_id=user_id,
            display_title="Damage Assessment Report Generated",
            history_payload=history_payload,
        )

        # ----- 7. Persist report_payload (single source of truth for the slider) -----
        first_prediction = all_predictions[0] if all_predictions else {}
        first_conf = 0
        try:
            cv = float(first_prediction.get("confidence", 0) or 0)
            first_conf = int(round((cv * 100) if cv <= 1 else cv))
        except Exception:
            first_conf = 0

        latest_report.damage_side = first_prediction.get("side", "") or ""
        latest_report.area_of_damage = first_prediction.get("part", "") or ""
        latest_report.type_of_damage = first_prediction.get("damage_type", "") or ""
        latest_report.severity = first_prediction.get("severity", "") or ""
        latest_report.confidence_percent = first_conf
        latest_report.total_damaged_points_identified = prediction_count
        latest_report.pdf_report_url = pdf_presigned_url
        latest_report.updated_by = user_id
        latest_report.updated_at = datetime.utcnow()

        latest_report.raw_result = {
            "predictions": all_predictions,
            "images": restored_images,
            "count": prediction_count,
            "high_severity_count": high_severity_count,
        }
        latest_report.report_payload = {
            "report_id": report_id,
            "assessmentType": assessment_type,
            "selectedImageIndex": 0,
            "images": restored_images,
            "all_predictions": all_predictions,
            "count": prediction_count,
            "high_severity_count": high_severity_count,
            "report_pdf_s3_key": pdf_upload["s3_key"],
            "report_pdf_url": pdf_presigned_url,
            "generated_at": generated_at_iso,
            "uploaded_by": handler_name,
            "source_name": "Claim Portal",
            "audit_trail": audit_trail,
            "case_document_id": case_document.id,
        }

        db.add(latest_report)
        db.commit()
        db.refresh(latest_report)

        return {
            "report_id": latest_report.id,
            "claim_id": claim_id,
            "predictions": all_predictions,
            "images": restored_images,
            "report_payload": latest_report.report_payload,
            "pdf_report_url": pdf_presigned_url,
            "count": prediction_count,
            "high_severity_count": high_severity_count,
        }

    # -----------------------------------------------------------------
    # SYNC PDF (manual re-upload path, kept for backward compat)
    # -----------------------------------------------------------------
    @staticmethod
    def sync_pdf_and_payload(
        claim_id: int,
        file: UploadFile,
        report_payload: str,
        db: Session,
        user_id: int,
    ):
        latest_report = (
            db.query(VehicleDamageAIReport)
            .filter(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.is_latest == True,
                VehicleDamageAIReport.is_deleted == False,
            )
            .order_by(VehicleDamageAIReport.version.desc(), VehicleDamageAIReport.id.desc())
            .first()
        )
        if not latest_report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No latest AI report exists for this claim. Analyze and save damage data first.",
            )

        try:
            parsed_payload = json.loads(report_payload) if report_payload else None
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="report_payload must be valid JSON.",
            )

        s3_service = S3Service()
        pdf_bytes = file.file.read()
        upload_result = s3_service.upload_ai_report_pdf_bytes(
            pdf_bytes=pdf_bytes,
            claim_id=claim_id,
            file_name=file.filename or "AI_Damage_Report.pdf",
        )
        presigned = s3_service.generate_presigned_download_url(upload_result["s3_key"])

        # The CaseDocument link lives in the ORIGINAL report_payload (set at
        # analyze time) — capture it before we overwrite the payload below.
        prev_payload = latest_report.report_payload if isinstance(latest_report.report_payload, dict) else {}
        case_document_id = prev_payload.get("case_document_id")

        latest_report.pdf_report_url = presigned
        if isinstance(parsed_payload, dict):
            parsed_payload["report_pdf_s3_key"] = upload_result["s3_key"]
            parsed_payload["report_pdf_url"] = presigned
            if case_document_id is not None:
                parsed_payload["case_document_id"] = case_document_id
        latest_report.report_payload = parsed_payload
        latest_report.updated_by = user_id
        latest_report.updated_at = datetime.utcnow()

        # Re-point the AI-report CaseDocument (what the Documents Library lists)
        # to the newly uploaded PDF, so the library shows the same file the user
        # saved instead of the original auto-generated one.
        if case_document_id:
            case_doc = (
                db.query(CaseDocument)
                .filter(CaseDocument.id == case_document_id)
                .first()
            )
            if case_doc:
                case_doc.s3_key = upload_result["s3_key"]
                case_doc.file_url = upload_result.get("file_url")
                case_doc.file_name = upload_result["s3_key"].split("/")[-1]
                case_doc.file_size_bytes = len(pdf_bytes)
                case_doc.updated_by = user_id
                case_doc.updated_at = datetime.utcnow()
                db.add(case_doc)

        db.add(latest_report)
        db.commit()
        db.refresh(latest_report)

        return {
            "report_id": latest_report.id,
            "pdf_report_url": presigned,
            "message": "AI report PDF and payload saved successfully.",
        }

    # -----------------------------------------------------------------
    # REGENERATE PDF with manual adjustments (server-side ReportLab)
    # -----------------------------------------------------------------
    @staticmethod
    def regenerate_pdf_with_adjustments(
        claim_id: int,
        manual_adjustments: dict,
        db: Session,
        user_id: int,
    ):
        """Rebuild the consolidated AI report PDF on the server (ReportLab) with
        the handler's manual adjustments (accept/reject decisions, notes, vehicle
        status), re-upload it to S3, and re-point the AI-report CaseDocument so the
        Documents Library shows the updated file. The frontend never renders the
        PDF — this is the secure backend path."""
        if not claim_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="claim_id is required.",
            )

        latest_report = (
            db.query(VehicleDamageAIReport)
            .filter(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.is_latest == True,
                VehicleDamageAIReport.is_deleted == False,
            )
            .order_by(VehicleDamageAIReport.version.desc(), VehicleDamageAIReport.id.desc())
            .first()
        )
        if not latest_report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No AI report exists for this claim. Analyze the damage first.",
            )

        payload = latest_report.report_payload if isinstance(latest_report.report_payload, dict) else {}
        s3_service = S3Service()

        # Refresh per-image presigned URLs from stored S3 keys so the PDF builder
        # (which downloads each image by URL) can fetch them.
        processed_images = []
        for item in payload.get("images") or []:
            pi = dict(item)
            if item.get("original_image_s3_key"):
                pi["original_image_url"] = s3_service.generate_presigned_download_url(item["original_image_s3_key"])
            if item.get("annotated_image_s3_key"):
                pi["annotated_image_url"] = s3_service.generate_presigned_download_url(item["annotated_image_s3_key"])
            processed_images.append(pi)

        all_predictions = payload.get("all_predictions") or []
        assessment_type = payload.get("assessmentType") or "-"
        report_id = payload.get("report_id") or AIReportPDFService.generate_report_id()
        client_name = VehicleDamageAIReportService._get_client_name(claim_id, db)
        handler_name = handler_name_for_user(db, user_id) or "Claim Handler"
        case_reference = build_case_reference(claim_id, db)
        generated_at_iso = payload.get("generated_at") or datetime.utcnow().isoformat()

        # Append an audit entry recording this manual edit (by the handler).
        audit_trail = list(payload.get("audit_trail") or [])
        audit_trail.append({
            "doneBy": handler_name,
            "action": "Manual Adjustments Saved",
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Vehicle cards (client + third party) for the report header.
        client_vehicle = None
        third_party_vehicle = None
        cv = db.query(VehicleDetail).filter(VehicleDetail.claim_id == claim_id).first()
        if cv:
            client_vehicle = {
                "registration": getattr(cv, "registration", None),
                "make": getattr(cv, "make", None),
                "model": getattr(cv, "model", None),
                "year": getattr(cv, "year", None) or getattr(cv, "manufacture_year", None),
                "color": getattr(cv, "color", None) or getattr(cv, "colour", None),
            }
            # Third party make/model/reg come from the third party vehicle area
            # on the vehicle details screen; if more than one, take the latest.
            tpv = (
                db.query(ThirdPartyVehicle)
                .filter(
                    ThirdPartyVehicle.client_vehicle_id == cv.id,
                    ThirdPartyVehicle.is_deleted == False,
                )
                .order_by(
                    ThirdPartyVehicle.created_at.desc(),
                    ThirdPartyVehicle.id.desc(),
                )
                .first()
            )
            if tpv:
                third_party_vehicle = {
                    "registration": getattr(tpv, "registration", None),
                    "make": getattr(tpv, "make", None),
                    "model": getattr(tpv, "model", None),
                    "year": getattr(tpv, "year", None),
                    "color": getattr(tpv, "color", None) or getattr(tpv, "colour", None),
                }

        pdf_bytes = AIReportPDFService.build_collective_pdf_bytes(
            claim_reference=case_reference,
            images=processed_images,
            predictions=all_predictions,
            report_id=report_id,
            generated_at=generated_at_iso,
            uploaded_by=payload.get("uploaded_by") or handler_name,
            source_name=payload.get("source_name") or "Claim Portal",
            assessment_type=assessment_type,
            audit_trail=audit_trail,
            client_vehicle=client_vehicle,
            third_party_vehicle=third_party_vehicle,
            manual_adjustments=manual_adjustments,
        )

        pdf_upload = s3_service.upload_ai_report_pdf_bytes(
            pdf_bytes=pdf_bytes,
            claim_id=claim_id,
            file_name=f"{report_id}_AI_Damage_Report.pdf",
        )
        presigned = s3_service.generate_presigned_download_url(pdf_upload["s3_key"])

        # Persist the adjustments (so they prefill next time) + the new PDF pointer.
        new_payload = {
            **payload,
            "manual_adjustments": manual_adjustments,
            "report_pdf_s3_key": pdf_upload["s3_key"],
            "report_pdf_url": presigned,
            "audit_trail": audit_trail,
        }
        latest_report.report_payload = new_payload
        latest_report.pdf_report_url = presigned
        latest_report.updated_by = user_id
        latest_report.updated_at = datetime.utcnow()

        # Re-point the AI-report CaseDocument (what the Documents Library lists).
        case_document_id = payload.get("case_document_id")
        if case_document_id:
            case_doc = (
                db.query(CaseDocument)
                .filter(CaseDocument.id == case_document_id)
                .first()
            )
            if case_doc:
                case_doc.s3_key = pdf_upload["s3_key"]
                case_doc.file_url = pdf_upload.get("file_url")
                case_doc.file_name = pdf_upload["s3_key"].split("/")[-1]
                case_doc.file_size_bytes = len(pdf_bytes)
                case_doc.updated_by = user_id
                case_doc.updated_at = datetime.utcnow()
                db.add(case_doc)

        db.add(latest_report)
        db.commit()
        db.refresh(latest_report)

        return {
            "report_id": latest_report.id,
            "pdf_report_url": presigned,
            "report_payload": latest_report.report_payload,
            "message": "Manual adjustments saved and report regenerated.",
        }

    # -----------------------------------------------------------------
    # SAVE / UPDATE single-row analysis payload
    # -----------------------------------------------------------------
    @staticmethod
    def save_or_update_analysis_payload(payload: dict, db: Session, user_id: int):
        claim_id = payload.get("claim_id")
        if not claim_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="claim_id is required.",
            )

        latest_report = (
            db.query(VehicleDamageAIReport)
            .filter(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.is_latest == True,
                VehicleDamageAIReport.is_deleted == False,
            )
            .order_by(VehicleDamageAIReport.version.desc(), VehicleDamageAIReport.id.desc())
            .first()
        )

        if latest_report:
            latest_report.damage_side = payload.get("damage_side", latest_report.damage_side)
            latest_report.area_of_damage = payload.get("area_of_damage", latest_report.area_of_damage)
            latest_report.severity = payload.get("severity", latest_report.severity)
            latest_report.confidence_percent = payload.get("confidence_percent", latest_report.confidence_percent)
            latest_report.updated_by = user_id
            latest_report.updated_at = datetime.utcnow()
            db.add(latest_report)
            db.commit()
            db.refresh(latest_report)
            return {"report_id": latest_report.id, "message": "AI damage details updated successfully."}

        report = VehicleDamageAIReport(
            claim_id=claim_id,
            damage_side=payload.get("damage_side", ""),
            area_of_damage=payload.get("area_of_damage", ""),
            severity=payload.get("severity", ""),
            confidence_percent=payload.get("confidence_percent", 0),
            version=1,
            is_latest=True,
            is_deleted=False,
            created_by=user_id,
            updated_by=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return {"report_id": report.id, "message": "AI damage details saved successfully."}

    # -----------------------------------------------------------------
    # helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _get_client_name(claim_id: int, db: Session) -> str:
        client = (
            db.query(ClientDetail)
            .filter(
                ClientDetail.claim_id == claim_id,
                ClientDetail.role == PersonRoleEnum.CLIENT,
            )
            .first()
        )
        if not client:
            return "Client"
        return f"{client.first_name or ''} {client.surname or ''}".strip() or "Client"

    @staticmethod
    def _build_ai_history_payload(
        client_name: str,
        image_name: str,
        assessment_type: str,
        prediction_count: int,
        high_severity_count: int,
        generated_at: str,
        report_id: Optional[int],
        case_document_id: Optional[int] = None,
    ) -> str:
        return json.dumps({
            "title": "Damage Assessment Report Generated",
            "badge": "AI Report",
            "system_name": "AI Analysis System",
            "client_name": client_name,
            "image_name": image_name,
            "assessment_type": assessment_type,
            "prediction_count": prediction_count,
            "high_severity_count": high_severity_count,
            "generated_at": generated_at,
            "report_id": report_id,
            "case_document_id": case_document_id,
            "document_type": "ai_report",
            "viewer_type": "slider",
            "message": "AI damage assessment report generated successfully.",
        })

    @staticmethod
    def _create_case_document_for_ai_report(
        *,
        db: Session,
        claim_id: int,
        tenant_id: int,
        user_id: int,
        client_name: str,
        image_name: str,
        assessment_type: str,
        prediction_count: int,
        high_severity_count: int,
        report_id: int,
        generated_at: datetime,
        pdf_upload: dict,
        pdf_bytes: bytes,
    ) -> CaseDocument:
        filename = pdf_upload["s3_key"].split("/")[-1]
        ext = Path(filename).suffix.lower() or ".pdf"

        document = CaseDocument(
            claim_id=claim_id,
            file_name=filename,
            original_filename=f"AI Damage Report - {image_name or 'Image'}.pdf",
            file_extension=ext,
            content_type="application/pdf",
            file_size_bytes=len(pdf_bytes),
            category="AI Report",
            tag="damage-assessment",
            source_type="ai_report",
            s3_key=pdf_upload["s3_key"],
            file_url=pdf_upload.get("file_url"),
            version=1,
            is_latest=True,
            is_active=True,
            is_deleted=False,
            tenant_id=tenant_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by=user_id,
            updated_by=user_id,
            metadata_json={
                "report_id": report_id,
                "claim_id": claim_id,
                "client_name": client_name,
                "generated_at": generated_at.isoformat(),
                "assessment_type": assessment_type,
                "prediction_count": prediction_count,
                "high_severity_count": high_severity_count,
                "preview_type": "pdf",
                "viewer_type": "slider",
                "document_role": "ai_damage_report",
            },
        )
        db.add(document)
        db.flush()
        db.refresh(document)

        audit_log = CaseDocumentAuditLog(
            case_document_id=document.id,
            action="upload",
            action_detail="AI report generated and stored automatically.",
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(audit_log)
        db.flush()
        return document

    @staticmethod
    def _create_ai_report_history(
        *,
        db: Session,
        claim_id: int,
        tenant_id: int,
        user_id: int,
        display_title: str,
        history_payload: str,
    ):
        history = HistoryActivities(
            claim_id=claim_id,
            tenant_id=tenant_id,
            file_name=display_title,
            file_path=history_payload,
            file_type=HistoryLogType.AI_REPORT,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(history)
        db.flush()
        db.refresh(history)
        return history
