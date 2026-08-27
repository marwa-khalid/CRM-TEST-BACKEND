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


def _log_vm(db: Session, record, action_type, details: str, actor: int | None,
            subject: str | None = None) -> None:
    from appflow.services.case_history_service import CaseHistoryService
    CaseHistoryService.log_document_record(
        db,
        record.id,
        action_type=action_type,
        details=details,
        subject=subject,
        documents=None,
        source="note",
        current_user=actor,
        scope_type=_scope_type(record),
        scope_id=record.id,
    )


def _log_vm_note(db: Session, record, details: str, actor: int | None) -> None:
    from libdata.enums import CaseHistoryActionType
    _log_vm(db, record, CaseHistoryActionType.NOTE, details, actor)


def log_vm_licensing_milestones(db: Session, record, changed_keys, authority, actor: int | None) -> None:
    """Auto-log plating/MOT milestones on the vehicle's history when they're set/
    changed on the licensing screen. Booked appointments — future calendar events —
    are logged as Diary (DY) entries (e.g. "Birmingham Plating Booked 13/02/2026");
    passed / expiry milestones are logged as Notes (NT) (e.g. "MOT Passed").
    ``authority`` is the saved licensing-authority; ``changed_keys`` the fields touched."""
    try:
        from libdata.enums import CaseHistoryActionType
        keys = set(changed_keys or [])
        la = (getattr(authority, "licensing_authority", "") or "").strip() or "Licensing Authority"

        def fmt(d):
            return d.strftime("%d/%m/%Y") if d else ""

        def val(name):
            return getattr(authority, name, None)

        # (action_type, details) events in document order.
        events = []
        if "plating_booked_date" in keys and val("plating_booked_date"):
            t = (val("plating_booked_time") or "").strip()
            events.append((CaseHistoryActionType.DIARY, f"{la} Plating Booked {fmt(val('plating_booked_date'))} {t}".strip()))
        if "plating_attended_passed" in keys and val("plating_attended_passed"):
            events.append((CaseHistoryActionType.NOTE, f"{la} Plating Appointment Passed"))
        if "plating_expiry_date" in keys and val("plating_expiry_date"):
            events.append((CaseHistoryActionType.NOTE, f"{la} Plate Exp {fmt(val('plating_expiry_date'))}"))
        if "mot_booked_date" in keys and val("mot_booked_date"):
            t = (val("mot_booked_time") or "").strip()
            events.append((CaseHistoryActionType.DIARY, f"{la} MOT Booked {fmt(val('mot_booked_date'))} {t}".strip()))
        if "mot_attended_passed" in keys and val("mot_attended_passed"):
            events.append((CaseHistoryActionType.NOTE, f"{la} MOT Passed"))
        if "mot_expiry_date" in keys and val("mot_expiry_date"):
            events.append((CaseHistoryActionType.NOTE, f"{la} MOT Exp {fmt(val('mot_expiry_date'))}"))

        for action_type, details in events:
            _log_vm(db, record, action_type, details, actor)
    except Exception as exc:  # noqa: BLE001 — never break the VM action
        print(f"[VM history] licensing milestone log failed: {exc}")


# Human labels for the vehicle_status values, and which read as an on/off-hire
# movement (MO) vs. a lifecycle status note (NT).
_VM_STATUS_LABELS = {
    "available": "Available",
    "weekly_hire": "On Hire",
    "on_hire": "On Hire",
    "sorn": "SORN",
    "sold": "Sold",
    "defleet": "De-fleeted",
    "de_fleet": "De-fleeted",
    "de-fleeted": "De-fleeted",
    "scrapped": "Scrapped",
    "off_road": "Off Road",
}


def log_vm_status_change(db: Session, record, old_status, new_status, actor: int | None) -> None:
    """Auto-log a VM vehicle status change to the vehicle's history — on/off-hire
    transitions as Movement (MO), lifecycle changes (SORN / Sold / De-fleeted) as
    Note (NT). Mirrors the legacy status ("SS") rows."""
    try:
        from libdata.enums import CaseHistoryActionType
        new_norm = (new_status or "").strip().lower().replace(" ", "_")
        old_norm = (old_status or "").strip().lower().replace(" ", "_")
        if not new_norm or new_norm == old_norm:
            return
        label = _VM_STATUS_LABELS.get(new_norm) or (new_status or "").strip().title()
        is_hire_movement = new_norm in ("weekly_hire", "on_hire", "available")
        if is_hire_movement:
            details = "Placed on hire" if new_norm in ("weekly_hire", "on_hire") else "Off-hired / returned to available"
            _log_vm(db, record, CaseHistoryActionType.MOVEMENT, details, actor,
                    subject="On Hire" if new_norm in ("weekly_hire", "on_hire") else "Off Hire")
        else:
            _log_vm(db, record, CaseHistoryActionType.NOTE, f"Vehicle status: {label}", actor,
                    subject="Status Change")
    except Exception as exc:  # noqa: BLE001 — never break the VM action
        print(f"[VM history] status-change log failed: {exc}")
