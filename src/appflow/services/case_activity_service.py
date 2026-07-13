import json
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from appflow.models.case_activity import CaseActivityAttachmentOut, CaseActivityItemOut
from appflow.services.microsoft_graph_token_service import MicrosoftGraphTokenService
from appflow.services.outlook_case_activity_service import OutlookCaseActivityService
from appflow.utils import build_case_reference
from libdata.models.tables import Claim, HistoryActivities, User, VehicleDamageAIReport


def _get_outlook_token(claim: Claim, db: Session) -> str:
    return MicrosoftGraphTokenService.get_access_token("read")


class CaseActivityService:
    @staticmethod
    def get_case_activity(
        claim_id: int,
        db: Session,
        include_emails: bool = True,
    ) -> List[CaseActivityItemOut]:
        history_items = CaseActivityService._get_history_items(claim_id, db)
        email_items = CaseActivityService._get_email_items(claim_id, db) if include_emails else []

        ai_reports = (
            db.query(VehicleDamageAIReport)
            .filter(
                VehicleDamageAIReport.claim_id == claim_id,
                VehicleDamageAIReport.is_active.is_(True),
                VehicleDamageAIReport.is_deleted.is_(False),
            )
            .order_by(VehicleDamageAIReport.created_at.desc())
            .all()
        )

        ai_items = [CaseActivityService._build_ai_report_item(ai_report) for ai_report in ai_reports]

        combined = history_items + email_items + ai_items
        combined.sort(key=lambda x: x.timestamp.isoformat() if x.timestamp else "", reverse=True)
        return combined

    @staticmethod
    def _get_history_items(claim_id: int, db: Session) -> List[CaseActivityItemOut]:
        rows = (
            db.query(
                HistoryActivities,
                func.coalesce(
                    func.nullif(
                        func.trim(
                            func.concat(
                                func.coalesce(User.first_name, ""),
                                " ",
                                func.coalesce(User.last_name, ""),
                            )
                        ),
                        "",
                    ),
                    User.user_name,
                ).label("created_by_name"),
            )
            .join(User, User.id == HistoryActivities.created_by, isouter=True)
            .filter(
                HistoryActivities.claim_id == claim_id,
                HistoryActivities.is_active.is_(True),
                HistoryActivities.is_deleted.is_(False),
            )
            .order_by(HistoryActivities.created_at.desc())
            .all()
        )

        items: List[CaseActivityItemOut] = []
        for history, created_by_name in rows:
            mapped = CaseActivityService._map_history_row_to_case_activity_item(
                history=history,
                created_by_name=(created_by_name or "").strip(),
            )
            if mapped:
                items.append(mapped)
        return items

    @staticmethod
    def _get_email_items(claim_id: int, db: Session) -> List[CaseActivityItemOut]:
        try:
            claim = db.query(Claim).filter(Claim.id == claim_id).first()
            if not claim:
                return []

            access_token = _get_outlook_token(claim, db)
            if not access_token:
                return []

            return OutlookCaseActivityService.get_case_emails(
                claim_reference=build_case_reference(claim.id, db),
                access_token=access_token,
            )
        except Exception as exc:
            print(f"[CaseActivityService] Outlook email error: {exc}")
            return []

    @staticmethod
    def _map_history_row_to_case_activity_item(
        history: HistoryActivities,
        created_by_name: Optional[str] = None,
    ) -> Optional[CaseActivityItemOut]:
        file_type = str(
            history.file_type.value if hasattr(history.file_type, "value") else history.file_type or ""
        )
        file_type_lower = file_type.lower()
        payload = CaseActivityService._parse_json(history.file_path)

        # The real AI report rows come from VehicleDamageAIReport.  Do not render
        # the lightweight history log as a System card with raw JSON.
        if file_type_lower == "ai_report":
            return None

        if payload and payload.get("source_type") == "ai_report_note":
            return CaseActivityService._build_note_item(history, created_by_name, payload, file_type)

        upload_source = (payload or {}).get("source_type", "")
        if (
            file_type_lower in {"history_upload", "uploaded_vehicle_owner", "engineer_detail"}
            or file_type_lower.startswith("historyupload")
            or file_type_lower.startswith("upload")
            or file_type_lower.startswith("download")
            or "upload" in upload_source
        ):
            return CaseActivityService._build_upload_item(history, created_by_name, payload, file_type)

        if "note" in file_type_lower:
            return CaseActivityService._build_note_item(history, created_by_name, payload, file_type)

        if file_type_lower == "witness_questionnaire_submitted":
            return CaseActivityService._build_witness_item(history, created_by_name, payload, file_type)

        if (
            file_type_lower.startswith("updated_")
            or file_type_lower.startswith("created_")
            or file_type_lower.startswith("deactivated_")
            or file_type_lower.startswith("deativated_")
        ):
            return CaseActivityService._build_update_item(history, created_by_name, payload, file_type)

        if "email" in file_type_lower or "instruct" in file_type_lower:
            return None

        return CaseActivityService._build_system_item(history, created_by_name, payload, file_type)

    @staticmethod
    def _build_ai_report_item(ai_report: VehicleDamageAIReport) -> CaseActivityItemOut:
        payload = ai_report.report_payload or {}
        if isinstance(payload, str):
            payload = CaseActivityService._parse_json(payload) or {}

        predictions = payload.get("all_predictions") or []
        damage_table: List[Dict[str, Any]] = []
        for prediction in predictions:
            confidence = prediction.get("confidence", 0)
            try:
                confidence = round(float(confidence) * 100)
            except Exception:
                confidence = prediction.get("confidence", "")

            damage_table.append({
                "damage_side": prediction.get("side") or prediction.get("damage_side") or "-",
                "area_of_damage": prediction.get("part") or prediction.get("area_of_damage") or "-",
                "type_of_damage": prediction.get("damage_type") or prediction.get("type_of_damage") or "-",
                "severity": prediction.get("severity") or "-",
                "confidence": confidence,
                "points": prediction.get("points") or 1,
                "suggested_repair": prediction.get("suggested_repair_action") or (
                    "Replace" if prediction.get("severity") == "High" else "Repair"
                ),
            })

        if not damage_table and getattr(ai_report, "damage_side", None):
            damage_table.append({
                "damage_side": getattr(ai_report, "damage_side", "") or "-",
                "area_of_damage": getattr(ai_report, "area_of_damage", "") or "-",
                "type_of_damage": getattr(ai_report, "type_of_damage", "") or "-",
                "severity": getattr(ai_report, "severity", "") or "-",
                "confidence": getattr(ai_report, "confidence_percent", "") or "-",
                "points": getattr(ai_report, "total_damaged_points_identified", "") or "-",
                "suggested_repair": getattr(ai_report, "suggested_repair_action", "") or "-",
            })

        pdf_url = (
            getattr(ai_report, "pdf_report_url", None)
            or payload.get("report_pdf_url")
            or payload.get("pdf_report_url")
            or ""
        )

        case_document_id = payload.get("case_document_id") or getattr(ai_report, "case_document_id", None)
        high_count = payload.get("high_severity_count") or sum(
            1 for row in damage_table if str(row.get("severity", "")).lower() == "high"
        )

        return CaseActivityItemOut(
            id=ai_report.id,
            type="AI Report",
            history_file_type="ai_report",
            title="Damage Assessment Report Generated",
            timestamp=ai_report.created_at,
            summary="AI damage assessment report generated successfully.",
            detail_text="AI damage assessment report generated successfully.",
            created_by_name="",
            sender_name="AI Analysis System",
            sender_email="system@claimflow.ai",
            received_at=ai_report.created_at,
            body_preview="",
            body_text="",
            subject="",
            attachments=[
                CaseActivityAttachmentOut(
                    file_name="AI Damage Report.pdf",
                    file_url=pdf_url,
                    file_size="",
                    case_document_id=case_document_id,
                )
            ] if pdf_url else [],
            meta={
                "source_type": "ai_report",
                "document_type": "ai_report",
                "claim_id": ai_report.claim_id,
                "report_id": ai_report.id,
                "case_document_id": case_document_id,
                "report_pdf_url": pdf_url,
                "report_pdf_s3_key": payload.get("report_pdf_s3_key", ""),
                "viewer_type": "slider",
                "badge": "AI Report",
                "system_name": "AI Analysis System",
                "client_name": payload.get("uploaded_by") or "-",
                "image_name": f"{len(payload.get('images') or [])} image(s)" if payload.get("images") else "",
                "assessment_type": payload.get("assessmentType") or payload.get("assessment_type") or "Client vehicle only",
                "prediction_count": len(damage_table),
                "high_severity_count": high_count,
                "generated_at": payload.get("generated_at") or getattr(ai_report, "created_at", None),
                "damage_table": damage_table,
            },
        )

    @staticmethod
    def _build_upload_item(history: HistoryActivities, created_by_name: str, payload: Optional[Dict[str, Any]], file_type: str) -> CaseActivityItemOut:
        payload = payload or {}

        file_name = (
            payload.get("file_name")
            or CaseActivityService._extract_quoted_filename(history.file_name or "")
            or history.file_name
            or "Uploaded attachment"
        )
        file_url = payload.get("file_url") or ""
        s3_key = payload.get("s3_key") or ""
        # Uploads that stored a plain path/URL in file_path (driver-check images,
        # document-library files) carry no JSON payload — fall back to that path
        # so the file stays openable (the presigned endpoint resolves local
        # /uploads keys, and driver-check paths are relative to /uploads/driver-checks).
        if not file_url and not s3_key:
            raw = (history.file_path or "").strip()
            if raw and not raw.startswith("{"):
                if raw.startswith("http") or raw.startswith("/uploads/"):
                    file_url = raw
                elif raw.startswith("/"):
                    file_url = f"/uploads/driver-checks{raw}"
                else:
                    file_url = raw
                s3_key = file_url
        case_document_id = payload.get("case_document_id")
        content_type = payload.get("content_type") or "application/octet-stream"
        preview_type = payload.get("preview_type") or ("pdf" if str(file_name).lower().endswith(".pdf") else "file")

        attachments = []
        if file_url or s3_key:
            attachments.append(CaseActivityAttachmentOut(
                file_name=file_name,
                file_url=file_url,
                file_size=payload.get("file_size") or "",
                case_document_id=case_document_id,
            ))

        return CaseActivityItemOut(
            id=history.id,
            type="Upload",
            history_file_type=file_type,
            title=f"{file_name} has been uploaded",
            timestamp=history.created_at,
            summary="",
            detail_text="",
            created_by_name=created_by_name or "",
            attachments=attachments,
            subject="",
            sender_name="",
            sender_email="",
            received_at=history.created_at,
            body_preview="",
            body_text="",
            meta={
                **payload,
                "claim_id": history.claim_id,
                "source_type": payload.get("source_type") or "history_upload",
                "file_name": file_name,
                "file_url": file_url,
                "s3_key": s3_key,
                "case_document_id": case_document_id,
                "content_type": content_type,
                "preview_type": preview_type,
            },
        )

    @staticmethod
    def _build_note_item(history: HistoryActivities, created_by_name: str, payload: Optional[Dict[str, Any]], file_type: str) -> CaseActivityItemOut:
        payload = payload or {}
        note_text = payload.get("note_text") or payload.get("detail_text") or history.file_path or ""
        return CaseActivityItemOut(
            id=history.id,
            type="Note",
            history_file_type=file_type,
            title=payload.get("title") or history.file_name or "Case Note",
            timestamp=history.created_at,
            summary=payload.get("summary") or "",
            detail_text=note_text,
            created_by_name=created_by_name or "",
            attachments=[],
            subject="",
            sender_name="",
            sender_email="",
            received_at=history.created_at,
            body_preview=note_text,
            body_text=note_text,
            meta={**payload, "claim_id": history.claim_id},
        )

    @staticmethod
    def _build_witness_item(history: HistoryActivities, created_by_name: str, payload: Optional[Dict[str, Any]], file_type: str) -> CaseActivityItemOut:
        payload = payload or {}
        attachments = []
        if payload.get("file_url"):
            attachments.append(CaseActivityAttachmentOut(
                file_name=payload.get("file_name") or "Witness Attachment",
                file_url=payload.get("file_url"),
                file_size=payload.get("file_size") or "",
                case_document_id=payload.get("case_document_id"),
            ))

        return CaseActivityItemOut(
            id=history.id,
            type="Witness",
            history_file_type=file_type,
            title=payload.get("title") or history.file_name or "Witness Submission",
            timestamp=history.created_at,
            summary=payload.get("summary") or "",
            detail_text=payload.get("detail_text") or history.file_path or "",
            created_by_name=created_by_name or "",
            attachments=attachments,
            subject="",
            sender_name=payload.get("sender_name") or "",
            sender_email=payload.get("sender_email") or "",
            received_at=history.created_at,
            body_preview="",
            body_text="",
            meta={**payload, "claim_id": history.claim_id},
        )

    @staticmethod
    def _build_update_item(history: HistoryActivities, created_by_name: str, payload: Optional[Dict[str, Any]], file_type: str) -> CaseActivityItemOut:
        modified_fields = CaseActivityService._extract_modified_fields(payload, history.file_path)
        detail_text = ", ".join(modified_fields) if modified_fields else (history.file_path or "")
        return CaseActivityItemOut(
            id=history.id,
            type="Update",
            history_file_type=file_type,
            title=history.file_name or "System Update",
            timestamp=history.created_at,
            summary="",
            detail_text=detail_text,
            created_by_name=created_by_name or "",
            attachments=[],
            subject="",
            sender_name="",
            sender_email="",
            received_at=history.created_at,
            body_preview="",
            body_text="",
            meta={
                **(payload or {}),
                "claim_id": history.claim_id,
                "modified_fields": modified_fields,
            },
        )

    @staticmethod
    def _build_system_item(history: HistoryActivities, created_by_name: str, payload: Optional[Dict[str, Any]], file_type: str) -> CaseActivityItemOut:
        return CaseActivityItemOut(
            id=history.id,
            type="System",
            history_file_type=file_type,
            title=(payload or {}).get("title") or history.file_name or "System Activity",
            timestamp=history.created_at,
            summary=(payload or {}).get("summary") or "",
            detail_text=(payload or {}).get("detail_text") or (history.file_path or ""),
            created_by_name=created_by_name or "",
            attachments=[],
            subject="",
            sender_name="",
            sender_email="",
            received_at=history.created_at,
            body_preview="",
            body_text="",
            meta={**(payload or {}), "claim_id": history.claim_id},
        )

    @staticmethod
    def _parse_json(value: Any) -> Optional[Dict[str, Any]]:
        if not value or not isinstance(value, str):
            return None
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    @staticmethod
    def _extract_modified_fields(payload: Optional[Dict[str, Any]], raw_value: Any) -> List[str]:
        payload = payload or {}
        for key in ("modified_fields", "changed_fields", "fields"):
            value = payload.get(key)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str) and value.strip():
                return [item.strip() for item in value.split(",") if item.strip()]

        if isinstance(raw_value, str) and raw_value.strip():
            parsed = CaseActivityService._parse_json(raw_value)
            if parsed:
                return CaseActivityService._extract_modified_fields(parsed, "")
            if not raw_value.strip().startswith("{"):
                return [item.strip() for item in raw_value.split(",") if item.strip()]
        return []

    @staticmethod
    def _extract_quoted_filename(title: str) -> str:
        if not title:
            return ""
        if '"' in title:
            parts = title.split('"')
            if len(parts) >= 3:
                return parts[1]
        return ""

    @staticmethod
    def self_or_default(payload: Dict[str, Any], key: str, default: str) -> str:
        value = payload.get(key)
        if value is None or value == "":
            return default
        return str(value)
