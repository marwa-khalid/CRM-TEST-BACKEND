"""Post VM (CAMS / Skyline) vehicle actions to the shared Case History as records,
scoped to the vehicle (scope_type = vm_cams | vm_skyline, scope_id = record id).
Best-effort — a logging failure never breaks the underlying VM action."""
from sqlalchemy.orm import Session


def _scope_type(record) -> str:
    return "vm_cams" if (getattr(record, "context", "") or "").lower() == "cams" else "vm_skyline"


def log_vm_imported_file(db: Session, record, *, file_name: str, data: bytes,
                         content_type: str | None, actor: int | None,
                         details: str | None = None) -> None:
    """Log an uploaded document (V5C, MOT cert, plate receipt, invoice, …) as an
    Imported File (IF) record on the vehicle's history, with the file previewable."""
    try:
        from appflow.services.case_history_service import CaseHistoryService
        from libdata.enums import CaseHistoryActionType
        CaseHistoryService.log_document_record(
            db,
            record.id,
            action_type=CaseHistoryActionType.IMPORTED_FILE,
            details=details or f"Imported file - {file_name}",
            subject=file_name,
            documents=[{
                "name": file_name,
                "data": data,
                "content_type": content_type or "application/octet-stream",
            }],
            source="document",
            current_user=actor,
            scope_type=_scope_type(record),
            scope_id=record.id,
        )
    except Exception as exc:  # noqa: BLE001 — never break the VM action
        print(f"[VM history] imported-file log failed: {exc}")


def _log_vm_note(db: Session, record, details: str, actor: int | None) -> None:
    from appflow.services.case_history_service import CaseHistoryService
    from libdata.enums import CaseHistoryActionType
    CaseHistoryService.log_document_record(
        db,
        record.id,
        action_type=CaseHistoryActionType.NOTE,
        details=details,
        subject=None,
        documents=None,
        source="note",
        current_user=actor,
        scope_type=_scope_type(record),
        scope_id=record.id,
    )


def log_vm_licensing_milestones(db: Session, record, changed_keys, authority, actor: int | None) -> None:
    """Auto-log plating/MOT milestones (booked, passed, expiry) as Note (NT) records
    on the vehicle's history when they're set/changed on the licensing screen —
    e.g. "Birmingham Plate Exp 13/02/2026", "MOT Passed". ``authority`` is the saved
    licensing-authority (response or ORM); ``changed_keys`` are the fields touched."""
    try:
        keys = set(changed_keys or [])
        la = (getattr(authority, "licensing_authority", "") or "").strip() or "Licensing Authority"

        def fmt(d):
            return d.strftime("%d/%m/%Y") if d else ""

        def val(name):
            return getattr(authority, name, None)

        events = []
        if "plating_booked_date" in keys and val("plating_booked_date"):
            t = (val("plating_booked_time") or "").strip()
            events.append(f"{la} Plating Booked {fmt(val('plating_booked_date'))} {t}".strip())
        if "plating_attended_passed" in keys and val("plating_attended_passed"):
            events.append(f"{la} Plating Appointment Passed")
        if "plating_expiry_date" in keys and val("plating_expiry_date"):
            events.append(f"{la} Plate Exp {fmt(val('plating_expiry_date'))}")
        if "mot_booked_date" in keys and val("mot_booked_date"):
            t = (val("mot_booked_time") or "").strip()
            events.append(f"{la} MOT Booked {fmt(val('mot_booked_date'))} {t}".strip())
        if "mot_attended_passed" in keys and val("mot_attended_passed"):
            events.append(f"{la} MOT Passed")
        if "mot_expiry_date" in keys and val("mot_expiry_date"):
            events.append(f"{la} MOT Exp {fmt(val('mot_expiry_date'))}")

        for details in events:
            _log_vm_note(db, record, details, actor)
    except Exception as exc:  # noqa: BLE001 — never break the VM action
        print(f"[VM history] licensing milestone log failed: {exc}")
