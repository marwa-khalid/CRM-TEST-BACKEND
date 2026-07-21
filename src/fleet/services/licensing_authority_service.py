"""Licensing authorities for a vehicle record (up to four per vehicle)."""
from datetime import date
from typing import List, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from fleet.deps import S3Service
from fleet.models.tables import FleetVehicleLicensingAuthority

MAX_AUTHORITIES = 4

# Which columns each certificate writes, so upload/remove stay symmetrical.
CERTIFICATE_FIELDS = {
    "plating": ("plating_certificate_name", "plating_certificate_key", "plating_certificate_url"),
    "mot": ("mot_certificate_name", "mot_certificate_key", "mot_certificate_url"),
}


def _base_query(db: Session, vehicle_record_id: int):
    return (
        db.query(FleetVehicleLicensingAuthority)
        .filter(FleetVehicleLicensingAuthority.vehicle_record_id == vehicle_record_id)
        .filter(FleetVehicleLicensingAuthority.is_deleted.isnot(True))
    )


def list_authorities(db: Session, vehicle_record_id: int) -> List[FleetVehicleLicensingAuthority]:
    return _base_query(db, vehicle_record_id).order_by(FleetVehicleLicensingAuthority.id).all()


def create_authority(
    db: Session, vehicle_record_id: int, actor: Optional[int] = None,
) -> FleetVehicleLicensingAuthority:
    existing = list_authorities(db, vehicle_record_id)
    if len(existing) >= MAX_AUTHORITIES:
        raise HTTPException(
            status_code=400,
            detail=f"A vehicle can have at most {MAX_AUTHORITIES} licensing authorities.",
        )
    # Position is the tab label ("Licensing Authority 2") — take the next free
    # slot rather than count+1, so deleting the middle one doesn't duplicate.
    used = {a.position for a in existing if a.position}
    position = next(p for p in range(1, MAX_AUTHORITIES + 1) if p not in used)
    authority = FleetVehicleLicensingAuthority(
        vehicle_record_id=vehicle_record_id, position=position,
        created_by=actor, updated_by=actor,
    )
    db.add(authority)
    db.commit()
    db.refresh(authority)
    return authority


def get_authority_or_404(
    db: Session, vehicle_record_id: int, authority_id: int,
) -> FleetVehicleLicensingAuthority:
    authority = _base_query(db, vehicle_record_id).filter(
        FleetVehicleLicensingAuthority.id == authority_id
    ).first()
    if not authority:
        raise HTTPException(status_code=404, detail="Licensing authority not found.")
    return authority


def update_authority(
    db: Session, vehicle_record_id: int, authority_id: int, payload: dict, actor: Optional[int] = None,
) -> FleetVehicleLicensingAuthority:
    authority = get_authority_or_404(db, vehicle_record_id, authority_id)
    for field, value in payload.items():
        if hasattr(authority, field):
            setattr(authority, field, value)
    authority.updated_by = actor
    db.commit()
    db.refresh(authority)
    # An expiry moving rebuilds its calendar event and restarts the reminder
    # schedule — uploading a newer certificate is what ends the old one.
    if {"plating_expiry_date", "mot_expiry_date"} & set(payload):
        from fleet.services import reminder_watcher
        if "plating_expiry_date" in payload:
            authority.plating_reminder_sent_on = None
        if "mot_expiry_date" in payload:
            authority.mot_reminder_sent_on = None
        db.commit()
        reminder_watcher.sync_authority_events(db, authority, actor)
        db.refresh(authority)
    return authority


def delete_authority(db: Session, vehicle_record_id: int, authority_id: int) -> None:
    authority = get_authority_or_404(db, vehicle_record_id, authority_id)
    authority.is_deleted = True
    db.commit()


def upload_certificate(
    db: Session, vehicle_record_id: int, authority_id: int, kind: str, file: UploadFile,
) -> FleetVehicleLicensingAuthority:
    if kind not in CERTIFICATE_FIELDS:
        raise HTTPException(status_code=400, detail="Unknown certificate type.")
    authority = get_authority_or_404(db, vehicle_record_id, authority_id)
    result = S3Service().upload_task_attachment_with_fallback(file)
    name_field, key_field, url_field = CERTIFICATE_FIELDS[kind]
    setattr(authority, name_field, getattr(file, "filename", None))
    setattr(authority, key_field, result.get("s3_key"))
    setattr(authority, url_field, result.get("file_url"))
    db.commit()
    db.refresh(authority)
    return authority


def remove_certificate(
    db: Session, vehicle_record_id: int, authority_id: int, kind: str,
) -> FleetVehicleLicensingAuthority:
    if kind not in CERTIFICATE_FIELDS:
        raise HTTPException(status_code=400, detail="Unknown certificate type.")
    authority = get_authority_or_404(db, vehicle_record_id, authority_id)
    # Only clears the file — the OCR'd values stay, since the user may have
    # amended them and "Remove & Upload Again" replaces the document, not the data.
    for field in CERTIFICATE_FIELDS[kind]:
        setattr(authority, field, None)
    db.commit()
    db.refresh(authority)
    return authority


def _fmt_date(value) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def build_letters_html(
    db: Session, record, authorities: List[FleetVehicleLicensingAuthority],
) -> str:
    """One Licensing Authority letter per authority, as a printable page.

    A single document with a page break between letters, so preview, print and
    print-to-PDF all work from one view — the same pattern as the hire-side
    generated documents.
    """
    from html import escape

    today = date.today().strftime("%d %B %Y")
    reg = (getattr(record, "registration_number", "") or "").strip() or "—"
    make = (getattr(record, "make", "") or "").strip()
    model = (getattr(record, "model", "") or "").strip()
    vehicle_line = " ".join(p for p in (make, model) if p) or "—"

    letters = []
    for authority in authorities:
        address_lines = [
            escape(authority.licensing_authority or "Licensing Authority"),
            *[escape(part.strip()) for part in (authority.address or "").split(",") if part.strip()],
            escape(authority.postcode or ""),
        ]
        letters.append(f"""
    <section class="letter">
      <div class="head">
        <div class="to">{'<br/>'.join(line for line in address_lines if line)}</div>
        <div class="meta"><strong>Skyline Car Hire (UK) Ltd</strong><br/>Date: {escape(today)}</div>
      </div>
      <p>Dear Sir or Madam,</p>
      <h2>Vehicle Licensing — {escape(reg)}</h2>
      <p>We write in respect of the following vehicle licensed with your authority.</p>
      <table>
        <tr><th>Registration</th><td>{escape(reg)}</td></tr>
        <tr><th>Vehicle</th><td>{escape(vehicle_line)}</td></tr>
        <tr><th>Plate number</th><td>{escape(authority.plate_number or '—')}</td></tr>
        <tr><th>Plating start date</th><td>{escape(_fmt_date(authority.plating_start_date) or '—')}</td></tr>
        <tr><th>Plating expiry date</th><td>{escape(_fmt_date(authority.plating_expiry_date) or '—')}</td></tr>
        <tr><th>Last MOT date</th><td>{escape(_fmt_date(authority.last_mot_date) or '—')}</td></tr>
        <tr><th>MOT expiry date</th><td>{escape(_fmt_date(authority.mot_expiry_date) or '—')}</td></tr>
      </table>
      <p>Please confirm the above details are correct and advise us of anything further you require.</p>
      <p class="sign">Yours faithfully,<br/><br/>Skyline Car Hire (UK) Ltd</p>
    </section>""")

    body = "".join(letters) or '<p class="empty">No licensing authorities have been added for this vehicle yet.</p>'
    count = len(authorities)
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Licensing Authority Letters</title>
    <style>
      *{{box-sizing:border-box}}
      body{{font-family:Arial,sans-serif;margin:24px;color:#111827;background:#fff}}
      header{{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e5e7eb;padding-bottom:14px;margin-bottom:20px}}
      h1{{font-size:22px;margin:0}}
      h2{{font-size:16px;margin:16px 0 10px}}
      button{{font:inherit;border:1px solid #111827;border-radius:4px;background:#111827;color:#fff;padding:10px 14px;cursor:pointer}}
      .letter{{break-after:page;margin-bottom:40px}}
      .letter:last-child{{break-after:auto}}
      .head{{display:flex;justify-content:space-between;gap:24px;margin-bottom:24px}}
      .to,.meta{{line-height:1.5;font-size:13px}}
      .meta{{text-align:right}}
      p{{margin:0 0 10px;line-height:1.5}}
      .sign{{margin-top:28px}}
      table{{border-collapse:collapse;width:100%;margin:8px 0 14px}}
      td,th{{border:1px solid #d1d5db;padding:6px 8px;font-size:13px;text-align:left}}
      th{{background:#f3f4f6;width:200px}}
      .empty{{color:#9ca3af}}
      @media print{{
        body{{margin:0}}
        header{{display:none}}
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>Licensing Authority Letters ({count})</h1>
      <button onclick="window.print()">Print</button>
    </header>
    {body}
  </body>
</html>"""
