import base64
import io
import os
import time
from datetime import datetime, timedelta,timezone
from email import message
from fastapi import APIRouter, Depends, HTTPException, Request,BackgroundTasks,Form, File, UploadFile
import json
from pydantic import BaseModel
from jinja2 import Template
from libdata.settings import get_session
from libauth.token_util import sign_jwt,decode_auth_token
from appflow.utils import actor_id, get_tenant_id, handler_name_for_claim, handler_name_for_user
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from sqlalchemy.orm import Session
from weasyprint import HTML
from dotenv import load_dotenv
from appflow.models.witness import WitnessEmailRequest, QuestionnaireSubmitRequest, UpdateQuestionnaireStatusRequest
from libdata.models.tables import Questionnaire, ClaimQuestionnaire
from fastapi.responses import FileResponse, StreamingResponse
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, TrackingSettings, ClickTracking,ContentId
from pathlib import Path
from appflow.services.history_activity_service import HistoryActivityService
from appflow.services.email_delivery import send_email as deliver_email
from libdata.enums import HistoryLogType
from sqlalchemy import text
from sendgrid.helpers.mail import Mail, To, ReplyTo
import json
from pathlib import Path
from appflow.services.s3_service import S3Service
from libdata.models.tables import CaseDocument
from starlette.datastructures import UploadFile as StarletteUploadFile
load_dotenv()

email_router = APIRouter(prefix="/witnesses", tags=["Witnesses Email"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

logo_path = os.path.join(BASE_DIR, "static", "logo.png")
with open(logo_path, "rb") as f:
    logo_data = f.read()

logo_encoded = base64.b64encode(logo_data).decode()



# --- helper to render HTML -> PDF ---
def render_pdf_from_html(template_str: str, context: dict) -> bytes:
    template = Template(template_str)
    rendered_html = template.render(**context)
    pdf_io = io.BytesIO()
    HTML(string=rendered_html).write_pdf(pdf_io)
    return pdf_io.getvalue()


def _fetch_image_data_uri(url: str, timeout: int = 6) -> str:
    """Fetch a static-map URL server-side and return a `data:` URI, or "" on any
    failure (403/timeout/non-image). We fetch it ourselves — rather than letting
    WeasyPrint fetch it — so the letter only ever embeds a real image and never
    renders a broken-image placeholder + alt text."""
    import urllib.request

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "NationwideAssistCRM/1.0 (witness-letter)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return ""
            ctype = resp.headers.get("Content-Type", "")
            if "image" not in ctype:
                return ""
            data = resp.read()
        if not data:
            return ""
        return f"data:{ctype};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return ""


def _geocode_location(location: str, timeout: int = 6):
    """Geocode free-text location -> (lat, lon) via OpenStreetMap Nominatim
    (keyless). Returns None on failure."""
    import urllib.request
    import urllib.parse

    try:
        q = urllib.parse.quote(location)
        url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
        req = urllib.request.Request(
            url, headers={"User-Agent": "NationwideAssistCRM/1.0 (witness-letter)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            arr = json.loads(resp.read().decode())
        if arr:
            return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception:
        pass
    return None


def _render_osm_tile_map(lat: float, lon: float, zoom: int = 15,
                         width: int = 520, height: int = 300) -> str:
    """Build a static map by stitching OpenStreetMap raster tiles centred on
    (lat, lon) and drawing a red marker, then return it as a PNG `data:` URI.
    Keyless and self-contained (uses OSM's canonical tile server). Returns "" if
    Pillow is unavailable or no tiles could be fetched."""
    import io as _io
    import math
    import urllib.request

    try:
        from PIL import Image, ImageDraw
    except Exception:
        return ""

    ua = {"User-Agent": "NationwideAssistCRM/1.0 (witness-letter)"}
    n = 2 ** zoom
    # Fractional world-pixel position of the point (256px tiles).
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    px, py = x * 256.0, y * 256.0
    left, top = px - width / 2.0, py - height / 2.0
    x0, x1 = math.floor(left / 256.0), math.floor((left + width) / 256.0)
    y0, y1 = math.floor(top / 256.0), math.floor((top + height) / 256.0)

    canvas = Image.new("RGB", (width, height), (233, 233, 233))
    pasted = 0
    try:
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                if ty < 0 or ty >= n:
                    continue
                url = f"https://tile.openstreetmap.org/{zoom}/{tx % n}/{ty}.png"
                try:
                    req = urllib.request.Request(url, headers=ua)
                    with urllib.request.urlopen(req, timeout=8) as r:
                        if "image" not in r.headers.get("Content-Type", ""):
                            continue
                        tile = Image.open(_io.BytesIO(r.read())).convert("RGB")
                except Exception:
                    continue
                canvas.paste(tile, (int(round(tx * 256 - left)), int(round(ty * 256 - top))))
                pasted += 1
        if pasted == 0:
            return ""
        # Red marker at the centre (the geocoded point).
        draw = ImageDraw.Draw(canvas)
        cx, cy, rad = width // 2, height // 2, 7
        draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad),
                     fill=(211, 47, 47), outline=(255, 255, 255), width=2)
        buf = _io.BytesIO()
        canvas.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


# Location snapshot for the witness letter — the same area the questionnaire
# canvas shows. Prefers Google Static Maps when a server-side-capable
# GOOGLE_MAPS_API_KEY is set; otherwise falls back to a keyless OpenStreetMap
# tile snapshot. Returns a `data:` URI (image embedded) or "" so the letter
# cleanly omits the map when nothing could be produced.
def build_location_map_src(location: str) -> str:
    import urllib.parse

    location = (location or "").strip()
    if not location:
        return ""

    # 1. Google Static Maps — only if a dedicated server key is set AND it works
    #    (a referrer-restricted frontend key returns 403 here, so we fall through).
    key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if key:
        center = urllib.parse.quote(location)
        g_url = (
            "https://maps.googleapis.com/maps/api/staticmap"
            f"?center={center}&zoom=15&size=600x300&scale=2"
            f"&markers=color:red%7C{center}&key={key}"
        )
        data_uri = _fetch_image_data_uri(g_url)
        if data_uri:
            return data_uri

    # 2. Keyless OpenStreetMap fallback — geocode, then stitch OSM tiles into a
    #    centred, marked snapshot with Pillow (no external static-map service).
    coords = _geocode_location(location)
    if coords:
        # Rendered smaller (crisp at the ~300px display width in the letter) so
        # the letter stays a single page.
        data_uri = _render_osm_tile_map(coords[0], coords[1], width=450, height=270)
        if data_uri:
            return data_uri

    return ""


@email_router.get("/questionnaire-preview")
def questionnaire_preview():
    """Return the witness questionnaire PDF template so the 'View' button can
    show the user how the emailed questionnaire looks (opened inline)."""
    path = os.path.join(TEMPLATE_DIR, "questionnaire.pdf")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Questionnaire template not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="questionnaire.pdf"'},
    )


# --- deep link token generator ---
def generate_deep_link_token(
    request: Request,
    claim_id: int,
    witness_id: int,
    claim_questionnaire_id: int
) -> str:
    user_id = actor_id(request)
    tenant_id = get_tenant_id(request)

    issue_time = datetime.utcnow()
    expiry_time = issue_time + timedelta(weeks=1)

    token_payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "claim_id": claim_id,
        "witness_id": witness_id,
        "claim_questionnaire_id": claim_questionnaire_id,
        "type": "witness_questionnaire",
        "iat": int(time.mktime(issue_time.timetuple())),
        "exp": int(time.mktime(expiry_time.timetuple())),
    }

    token = sign_jwt(token_payload)

    if isinstance(token, dict) and "access_token" in token:
        return token["access_token"]

    return token
# --- route to send email ---
# @email_router.post("/send-witness-email/{claim_id}")
# def send_witness_email(
#     claim_id: int,
#     data: WitnessEmailRequest,
#     request: Request,
#     db: Session = Depends(get_session)
# ):
#     # 1. fetch client details
#     client = db.execute(
#         """
#         SELECT 
#             cd.first_name,
#             cd.surname,
#             cd.date_of_birth,
#             cd.occupation,
#             a.address
#         FROM client_details cd
#         LEFT JOIN addresses a ON cd.address_id = a.id
#         WHERE cd.claim_id = :cid
#         """,
#         {"cid": claim_id}
#     ).fetchone()

#     if not client:
#         raise HTTPException(status_code=404, detail="Client not found")

#     # 2. prepare context
#     client_detail = {
#         "reference": data.reference,
#         "name": f"{client.first_name} {client.surname}",
#         "address": client.address or "",
#         "dob": client.date_of_birth.strftime("%d-%m-%Y") if client.date_of_birth else "",
#         "occupation": client.occupation or "",
#         "date": datetime.now().strftime("%d-%m-%Y"),
#         "witness_name": data.witness_name,
#         "witness_date": datetime.now().strftime("%d-%m-%Y")
#     }

#     # 3. Build Mail message depending on option
#     if data.option == "pdf":
#         # --- Option 1: Send as PDF attachments ---
#         with open(os.path.join(TEMPLATE_DIR, "letter.html"), "r", encoding="utf-8") as f:
#             letter_template = f.read()
#         with open(os.path.join(TEMPLATE_DIR, "questionnaire.html"), "r", encoding="utf-8") as f:
#             questionnaire_template = f.read()

#         questionnaire_pdf = render_pdf_from_html(questionnaire_template, client_detail)
#         letter_pdf = render_pdf_from_html(letter_template, client_detail)

#         questionnaire_encoded = base64.b64encode(questionnaire_pdf).decode()
#         letter_encoded = base64.b64encode(letter_pdf).decode()

#         message = Mail(
#             from_email="proclaim@yopmail.com",
#             to_emails=data.witness_email,
#             subject="Questionnaire & Letter",
#             html_content="Dear Witness,<br>Please find attached the questionnaire and letter."
#         )
#         message.attachment = [
#             Attachment(
#                 FileContent(questionnaire_encoded),
#                 FileName("questionnaire.pdf"),
#                 FileType("application/pdf"),
#                 Disposition("attachment")
#             ),
#             Attachment(
#                 FileContent(letter_encoded),
#                 FileName("letter.pdf"),
#                 FileType("application/pdf"),
#                 Disposition("attachment")
#             )
#         ]

#     elif data.option == "link":
#         # --- Option 2: Send secure digital form link ---
#         token = generate_deep_link_token(request, claim_id)
#         frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
#         link = f"{frontend_url}/questionnaire?details={token}"

#         message = Mail(
#             from_email="proclaim@yopmail.com",
#             to_emails=data.witness_email,
#             subject="Secure Link to Questionnaire",
#             html_content=f"""
#                 Dear {data.witness_name},<br><br>
#                 Please complete the online questionnaire by clicking the secure link below:<br><br>
#                 <a href="{link}">{link}</a><br><br>
#                 This link will expire in 7 days.<br><br>
#                 Regards,<br>Proclaim Team
#             """
#         )

#     else:
#         raise HTTPException(status_code=400, detail="Invalid option selected")

#     # 4. send email
#     try:
#         api_key = os.getenv("SENDGRID_API_KEY")
#         if not api_key:
#             raise HTTPException(status_code=500, detail="SendGrid API key not set in environment")

#         sg = SendGridAPIClient(api_key)
#         response = sg.send(message)
#         return {"status": "success", "sendgrid_status": response.status_code}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@email_router.post("/send-witness-email/{claim_id}")
def send_witness_email(
    claim_id: int,
    data: WitnessEmailRequest,
    request: Request,
    db: Session = Depends(get_session)
):
    print(claim_id)
    # 1. fetch client details
    client = db.execute(
    text("""
        SELECT 
            cd.first_name,
            cd.surname,
            cd.date_of_birth,
            cd.occupation,
            a.address,
            ad.date_time AS accident_time,
            ad.location AS accident_location,
            h.label AS handler_name
        FROM client_details cd
        LEFT JOIN addresses a ON cd.address_id = a.id
        LEFT JOIN accident_details ad ON cd.claim_id = ad.claim_id
        LEFT JOIN claims c ON cd.claim_id = c.id
        LEFT JOIN handlers h ON c.handler_id = h.id
        WHERE cd.claim_id = :cid 
        AND cd.role = 'CLIENT'
        AND cd.is_active = true
        LIMIT 1
    """),
    {"cid": claim_id}
).fetchone()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    print(client.first_name)

    # 2. prepare context
    client_detail = {
        "reference": data.reference,
        "client_name": f"{client.first_name} {client.surname}",
        "address": client.address or "",
        "dob": client.date_of_birth.strftime("%d-%m-%Y") if client.date_of_birth else "",
        "occupation": client.occupation or "",
        "date": datetime.now().strftime("%d-%m-%Y"),
        "witness_name": data.witness_name,
        "witness_date": datetime.now().strftime("%d-%m-%Y"),
        "accident_time": client.accident_time.strftime("%d-%m-%Y %H:%M") if client.accident_time else "",
        "accident_location": client.accident_location or "",
        "location_map_url": build_location_map_src(client.accident_location or ""),
        "handler_name": client.handler_name or "Claim Handler",
        "handler_title": "Claim Handler",
        "company_name": "Nationwide Assist",
        "name": data.witness_name,
    }

    # Witness's own address (recipient block on the letter). Looked up from the
    # witness client_details row when we have its id.
    witness_address = ""
    if getattr(data, "witness_id", None):
        wrow = db.execute(
            text(
                "SELECT a.address FROM client_details cd "
                "LEFT JOIN addresses a ON cd.address_id = a.id WHERE cd.id = :wid"
            ),
            {"wid": data.witness_id},
        ).fetchone()
        witness_address = (getattr(wrow, "address", "") if wrow else "") or ""
    client_detail["witness_address"] = witness_address

    # Claim handler shown on the letter = the claim's handler (the logged-in
    # user's name / email handle), not a hardcoded name.
    from libdata.models.tables import Claim as _Claim
    _claim_obj = db.query(_Claim).filter(_Claim.id == claim_id).first()
    _handler = (
        handler_name_for_user(db, actor_id(request))
        or (handler_name_for_claim(_claim_obj, db) if _claim_obj else "")
    )
    if _handler:
        client_detail["handler_name"] = _handler

    # Personalise the blank questionnaire with the witness's own ref/name/address
    # (dob & occupation stay blank for the witness to complete by hand).
    questionnaire_context = {
        **client_detail,
        "reference": data.reference,
        "name": data.witness_name,
        "address": witness_address,
        "dob": "",
        "occupation": "",
    }
    with open(os.path.join(TEMPLATE_DIR, "questionnaire.html"), "r", encoding="utf-8") as _qf:
        _questionnaire_template = _qf.read()
    questionnaire_pdf_bytes = render_pdf_from_html(_questionnaire_template, questionnaire_context)

    result = {
        "claim_id": claim_id,
        "option": data.option,
        "client_detail": client_detail
    }

    # 3. Build response depending on option
    if data.option == "pdf":
        # 1. Handle the HTML letter (needs rendering)
        with open(os.path.join(TEMPLATE_DIR, "letter.html"), "r", encoding="utf-8") as f:
            letter_template = f.read()
        letter_pdf = render_pdf_from_html(letter_template, client_detail)

        # 2. Personalised questionnaire (rendered with the witness's ref/name/address)
        questionnaire_pdf_content = questionnaire_pdf_bytes

        # 3. Base64 encode the binary contents
        # letter_pdf is already bytes from render_pdf_from_html
        letter_encoded = base64.b64encode(letter_pdf).decode()
        # questionnaire_pdf_content is bytes from "rb"
        questionnaire_encoded = base64.b64encode(questionnaire_pdf_content).decode()

        # --- DATABASE & EMAIL LOGIC ---
        claim = db.execute(
            text("""
                SELECT c.id, c.file_opened_at, cd.surname AS client_surname
                FROM claims c
                JOIN client_details cd ON cd.claim_id = c.id AND cd.role = 'CLIENT'
                WHERE c.id = :cid
            """),
            {"cid": claim_id}
        ).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        year_month = datetime.now().strftime("%Y%m")
        case_reference = f"{client.surname}-{year_month}-{claim.id:04d}"
        # Format: 02-12-26 / 5:35 PM
        submission_time = datetime.now().strftime("%d-%m-%y / %I:%M %p")

        # Case Reference: 202602-0015

        logo_inline_src = f"data:image/png;base64,{logo_encoded}"
        witness_html = f"""
                                        <html>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: Arial, sans-serif;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                
                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 30px;">
                    <tr>
                        <td align="center">
                            <img src="{logo_inline_src}" alt="Nationwide Assist" width="60" style="display: block; border: 0;">
                        </td>
                    </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; margin-bottom: 16px;">
                    <tr>
                        <td align="center" style="font-size: 16px; font-weight: 600; color: #000000;">
                            Dear {data.witness_name}
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding-top: 12px; font-size: 14px; font-weight: 400; color: #444444; line-height: 1.5;">
                            Please find attached the questionnaire and cover letter for:
                        </td>
                    </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="16" style="max-width: 420px; border: 1px solid #CCCCCC; border-radius: 8px; background-color: #ffffff;">
                    <tr>
                        <td>
                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td width="160" style="color: #444444; font-size: 12px; font-weight: 400;">Case Reference:</td>
                                    <td style="color: #444444; font-size: 12px; font-weight: 600;">{data.reference}</td>
                                </tr>
                                <tr><td colspan="2" style="padding: 8px 0;"><div style="height: 1px; background-color: #CCCCCC;"></div></td></tr>
                                
                                <tr>
                                    <td width="160" style="color: #444444; font-size: 12px; font-weight: 400;">Witness Name</td>
                                    <td style="color: #444444; font-size: 12px; font-weight: 600;">{data.witness_name}</td>
                                </tr>
                               
                            </table>
                        </td>
                    </tr>
                </table>


                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; margin-top: 40px;">
                    <tr><td style="height: 1px; background-color: #CCCCCC;"></td></tr>
                    <tr>
                        <td align="center" style="padding-top: 24px; color: #444444;">
                            <span style="font-size: 12px; font-weight: 600;">Kind regards,</span><br/>
                            <span style="font-size: 14px; font-weight: 600; display: inline-block; margin-top: 4px;">Nationwide Assist IT / Systems Team</span>
                        </td>
                    </tr>
                </table>

            </td>
        </tr>
    </table>
</body>
</html>
                                    """
        witness_attachments = [
            {"name": "questionnaire.pdf", "content_bytes": questionnaire_encoded, "content_type": "application/pdf"},
            {"name": "letter.pdf", "content_bytes": letter_encoded, "content_type": "application/pdf"},
        ]

        # Use provided witness_id directly if available, else fall back to email lookup
        if data.witness_id:
            witness_row = db.execute(
                text("SELECT id FROM client_details WHERE id = :wid AND is_active = true"),
                {"wid": data.witness_id}
            ).fetchone()
        else:
            witness_row = db.execute(
                text("""
                    SELECT cd.id
                    FROM client_details cd
                    LEFT JOIN addresses a ON cd.address_id = a.id
                    WHERE cd.claim_id = :cid
                    AND cd.role = 'WITNESS'
                    AND LOWER(TRIM(a.email)) = LOWER(TRIM(:email))
                    AND cd.is_active = true
                    ORDER BY cd.id DESC
                    LIMIT 1
                """),
                {"cid": claim_id, "email": data.witness_email}
            ).fetchone()

            if not witness_row:
                address_result = db.execute(
                    text("INSERT INTO addresses (email, created_at) VALUES (:email, NOW()) RETURNING id"),
                    {"email": data.witness_email}
                ).fetchone()
                name_parts = (data.witness_name or "").strip().split(" ", 1)
                witness_row = db.execute(
                    text("""
                        INSERT INTO client_details
                            (claim_id, role, is_active, first_name, surname, address_id, created_at)
                        VALUES (:cid, 'WITNESS', true, :fn, :sn, :aid, NOW())
                        RETURNING id
                    """),
                    {
                        "cid": claim_id,
                        "fn": name_parts[0] if name_parts else "",
                        "sn": name_parts[1] if len(name_parts) > 1 else "",
                        "aid": address_result.id,
                    }
                ).fetchone()
                db.flush()

        pdf_questionnaire = ClaimQuestionnaire(
            claim_id=claim_id,
            witness_id=witness_row.id,
            status="sent",
            witness_name=data.witness_name,
            created_by=actor_id(request),
            sent_at=datetime.utcnow(),
        )
        db.add(pdf_questionnaire)
        db.flush()

        # send (Graph-first so it reaches Outlook, SendGrid fallback)
        deliver_email(
            to=data.witness_email,
            subject=f"Witness Questionnaire - Case Ref: {data.reference}",
            html=witness_html,
            attachments=witness_attachments,
        )

        db.commit()
        return {"status": "success", "claim_questionnaire_id": pdf_questionnaire.id}

        # --- Option 2: Secure Link ---
    elif data.option == "link":
        # Use provided witness_id directly if available, else fall back to email lookup
        if data.witness_id:
            witness = db.execute(
                text("SELECT id FROM client_details WHERE id = :wid AND is_active = true"),
                {"wid": data.witness_id}
            ).fetchone()
        else:
            witness = db.execute(
                text("""
                    SELECT cd.id
                    FROM client_details cd
                    LEFT JOIN addresses a ON cd.address_id = a.id
                    WHERE cd.claim_id = :cid
                    AND cd.role = 'WITNESS'
                    AND LOWER(TRIM(a.email)) = LOWER(TRIM(:email))
                    AND cd.is_active = true
                    ORDER BY cd.id DESC
                    LIMIT 1
                """),
                {"cid": claim_id, "email": data.witness_email}
            ).fetchone()

            if not witness:
                address_result = db.execute(
                    text("""
                        INSERT INTO addresses (email, created_at)
                        VALUES (:email, NOW())
                        RETURNING id
                    """),
                    {"email": data.witness_email}
                ).fetchone()

                name_parts = (data.witness_name or "").strip().split(" ", 1)
                first_name = name_parts[0] if name_parts else ""
                surname = name_parts[1] if len(name_parts) > 1 else ""

                witness_result = db.execute(
                    text("""
                        INSERT INTO client_details
                            (claim_id, role, is_active, first_name, surname, address_id, created_at)
                        VALUES
                            (:cid, 'WITNESS', true, :fn, :sn, :aid, NOW())
                        RETURNING id
                    """),
                    {"cid": claim_id, "fn": first_name, "sn": surname, "aid": address_result.id}
                ).fetchone()

                db.flush()
                witness = witness_result
        claim_questionnaire = ClaimQuestionnaire(
            claim_id=claim_id,
            witness_id=witness.id,
            status="sent",
            witness_name=data.witness_name,
            created_by=actor_id(request),
            sent_at=datetime.utcnow(),
        )

        db.add(claim_questionnaire)
        db.flush()

        token = generate_deep_link_token(
            request=request,
            claim_id=claim_id,
            witness_id=witness.id,
            claim_questionnaire_id=claim_questionnaire.id,
        )

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5174")
        link = f"{frontend_url}/questionnaire/{token}/step-1"

        logo_inline_src = f"data:image/png;base64,{logo_encoded}"
        expiry_date = (datetime.utcnow() + timedelta(days=7)).strftime("%d-%m-%Y")

        witness_link_html = f"""
        <html>
        <body style="margin:0; padding:0; background-color:#ffffff; font-family:Arial, sans-serif;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff;">
            <tr>
            <td align="center" style="padding:40px 20px;">

                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom:30px;">
                <tr>
                    <td align="center">
                    <img src="{logo_inline_src}" alt="Nationwide Assist" width="60" style="display:block; border:0;">
                    </td>
                </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:600px; margin-bottom:16px;">
                <tr>
                    <td align="center" style="font-size:16px; font-weight:600; color:#000000;">
                    Dear {data.witness_name}
                    </td>
                </tr>
                <tr>
                    <td align="center" style="padding-top:12px; font-size:14px; color:#444444; line-height:1.5;">
                    Please complete your witness questionnaire using the secure digital form link below.
                    </td>
                </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="16" style="max-width:420px; border:1px solid #CCCCCC; border-radius:8px; background-color:#ffffff;">
                <tr>
                    <td>
                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                        <tr>
                        <td width="160" style="color:#444444; font-size:12px;">Case Reference:</td>
                        <td style="color:#444444; font-size:12px; font-weight:600;">{data.reference}</td>
                        </tr>
                        <tr><td colspan="2" style="padding:8px 0;"><div style="height:1px; background-color:#CCCCCC;"></div></td></tr>

                        <tr>
                        <td width="160" style="color:#444444; font-size:12px;">Witness Name:</td>
                        <td style="color:#444444; font-size:12px; font-weight:600;">{data.witness_name}</td>
                        </tr>
                        <tr><td colspan="2" style="padding:8px 0;"><div style="height:1px; background-color:#CCCCCC;"></div></td></tr>

                        <tr>
                        <td width="160" style="color:#444444; font-size:12px;">Link Expiry:</td>
                        <td style="color:#444444; font-size:12px; font-weight:600;">{expiry_date}</td>
                        </tr>
                    </table>
                    </td>
                </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:380px; margin-top:30px;">
                <tr>
                    <td align="center" style="padding-bottom:20px; font-size:14px; color:#444444; line-height:1.5;">
                    This secure link will open the four-step witness questionnaire. You can complete and submit it online.
                    </td>
                </tr>
                <tr>
                    <td align="center">
                        <table border="0" cellspacing="0" cellpadding="0">
                        <tr>
                            <td
                            align="center"
                            bgcolor="#0352FD"
                            style="border-radius:4px; cursor:pointer;"
                            >
                            <a
                                href="{link}"
                                target="_blank"
                                rel="noopener noreferrer"
                                style="padding:16px 40px; font-size:16px; font-weight:500; color:#ffffff; text-decoration:none; display:inline-block; cursor:pointer;"
                            >
                                Complete Witness Questionnaire
                            </a>
                            </td>
                        </tr>
                        </table>
                    </td>
                </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:580px; margin-top:40px;">
                <tr><td style="height:1px; background-color:#CCCCCC;"></td></tr>
                <tr>
                    <td align="center" style="padding-top:24px; color:#444444;">
                    <span style="font-size:12px; font-weight:600;">Kind regards,</span><br/>
                    <span style="font-size:14px; font-weight:600; display:inline-block; margin-top:4px;">Nationwide Assist Team</span>
                    </td>
                </tr>
                </table>

            </td>
            </tr>
        </table>
        </body>
        </html>
        """

        # send (Graph-first so it reaches Outlook, SendGrid fallback)
        deliver_email(
            to=data.witness_email,
            subject=f"Witness Questionnaire - Case Ref: {data.reference}",
            html=witness_link_html,
        )

        db.commit()

        return {
            "status": "success",
            "option": "link",
            "questionnaire_status": "sent",
            "claim_questionnaire_id": claim_questionnaire.id,
            "deep_link": link,
        }
    elif data.option == "download":
        # Render letter dynamically
        with open(os.path.join(TEMPLATE_DIR, "letter.html"), "r", encoding="utf-8") as f:
            letter_template = f.read()
        letter_pdf = render_pdf_from_html(letter_template, client_detail)

        # Same personalised questionnaire the email attaches, so the postal
        # download matches exactly (with the witness's ref/name/address).
        questionnaire_pdf = questionnaire_pdf_bytes

        # Build ZIP
        import zipfile
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("Letter.pdf", letter_pdf)
            zipf.writestr("Questionnaire.pdf", questionnaire_pdf)
        zip_io.seek(0)
        zip_base64 = base64.b64encode(zip_io.read()).decode()

        # Track using witness_id directly if provided, else email lookup
        download_questionnaire_id = None
        if data.witness_id:
            dl_witness = db.execute(
                text("SELECT id FROM client_details WHERE id = :wid AND is_active = true"),
                {"wid": data.witness_id}
            ).fetchone()
        elif data.witness_email:
            dl_witness = db.execute(
                text("""
                    SELECT cd.id FROM client_details cd
                    LEFT JOIN addresses a ON cd.address_id = a.id
                    WHERE cd.claim_id = :cid AND cd.role = 'WITNESS'
                    AND LOWER(TRIM(a.email)) = LOWER(TRIM(:email)) AND cd.is_active = true
                    ORDER BY cd.id DESC LIMIT 1
                """),
                {"cid": claim_id, "email": data.witness_email}
            ).fetchone()
        else:
            dl_witness = None

        if dl_witness:
            dl_cq = ClaimQuestionnaire(
                claim_id=claim_id,
                witness_id=dl_witness.id,
                status="sent",
                witness_name=data.witness_name,
                created_by=actor_id(request),
                sent_at=datetime.utcnow(),
            )
            db.add(dl_cq)
            db.flush()
            download_questionnaire_id = dl_cq.id
            db.commit()

        result.update({
            "zip_base64": zip_base64,
            "filename": "Witness-Documents.zip",
            "claim_questionnaire_id": download_questionnaire_id,
        })
        return result
    else:
        raise HTTPException(status_code=400, detail="Invalid option selected")

    return result



# --- helper to send emails (Graph-first so they reach Outlook; SendGrid fallback) ---
def send_email(to_email: str, subject: str, html_content: str):
    deliver_email(to=to_email, subject=subject, html=html_content)

def get_logo_attachment():
    logo_confirm = os.path.join(BASE_DIR, "static", "logo.png")
    with open(logo_confirm, "rb") as f:
        logo_con = f.read()

    encoded = base64.b64encode(logo_con).decode()

    attachment = Attachment()
    attachment.file_content = FileContent(encoded)
    attachment.file_type = FileType("image/png")
    attachment.file_name = FileName("logo.png")
    attachment.disposition = Disposition("inline")
    attachment.content_id = ContentId("companylogo")
    return attachment
@email_router.post("/save")
async def save_questionnaire_by_link(
    request: Request,
    token: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
):
    # Parse the multipart form ourselves with a generous per-part limit — the
    # questionnaire's sketch snapshot and signature images are base64 strings
    # that routinely exceed Starlette's 1MB default (which 400s with
    # "Part exceeded maximum size of 1024KB").
    form = await request.form(max_part_size=25 * 1024 * 1024)
    status = form.get("status") or "completed"
    witness_sign = form.get("witness_sign")
    officer_sign = form.get("officer_sign")
    witness_name = form.get("witness_name")
    officer_name = form.get("officer_name")
    date_of_witness = form.get("date_of_witness")
    date_of_officer = form.get("date_of_officer")
    answers = form.get("answers") or "[]"
    witness_statement = form.get("witness_statement")
    _pf = form.get("pdf_file")
    pdf_file = _pf if isinstance(_pf, (UploadFile, StarletteUploadFile)) else None

    decoded = decode_auth_token(token)

    claim_id = decoded.get("claim_id")
    user_id = decoded.get("user_id")
    tenant_id = decoded.get("tenant_id")
    witness_id = decoded.get("witness_id")
    claim_questionnaire_id = decoded.get("claim_questionnaire_id")
    exp = decoded.get("exp")
    answers_data = json.loads(answers or "[]")

    if not claim_id or not user_id:
        raise HTTPException(status_code=400, detail="Invalid token")

    if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Token expired")

    claim = db.execute(
        text("""
            SELECT 
                c.id,
                c.file_opened_at,
                h.label AS handler_name,
                cd.surname AS client_surname
            FROM claims c
            LEFT JOIN handlers h ON h.id = c.handler_id
            JOIN client_details cd 
                ON cd.claim_id = c.id 
                AND cd.role = 'CLIENT'
                AND cd.is_active = true
            WHERE c.id = :cid
            LIMIT 1
        """),
        {"cid": claim_id}
    ).fetchone()

    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    year = claim.file_opened_at.strftime("%Y") if claim.file_opened_at else datetime.now().strftime("%Y")
    month = claim.file_opened_at.strftime("%m") if claim.file_opened_at else datetime.now().strftime("%m")
    padded_id = str(claim.id).zfill(5)
    case_reference = f"{claim.client_surname}-{year}{month}-{padded_id}"
    handler_name = claim.handler_name or "Claim Handler"

    if claim_questionnaire_id:
        claim_questionnaire = db.query(ClaimQuestionnaire).filter(
            ClaimQuestionnaire.id == claim_questionnaire_id
        ).first()
    else:
        claim_questionnaire = None

    if not claim_questionnaire:
        claim_questionnaire = ClaimQuestionnaire(
            claim_id=claim_id,
            witness_id=witness_id,
            created_by=user_id,
        )
        db.add(claim_questionnaire)
        db.flush()

    normalized_status = status or "completed"
    questionnaire_was_completed = (
        (claim_questionnaire.status or "").lower() == "completed"
        or bool(claim_questionnaire.completed_at)
    )

    claim_questionnaire.status = normalized_status
    claim_questionnaire.witness_sign = witness_sign
    claim_questionnaire.officer_sign = officer_sign
    claim_questionnaire.witness_name = witness_name
    claim_questionnaire.officer_name = officer_name
    claim_questionnaire.date_of_witness = date_of_witness
    claim_questionnaire.date_of_officer = date_of_officer
    claim_questionnaire.completed_at = datetime.utcnow()

    db.query(Questionnaire).filter(
        Questionnaire.claim_questionnaire_id == claim_questionnaire.id
    ).delete()

    for item in answers_data:
        q = Questionnaire(
            claim_questionnaire_id=claim_questionnaire.id,
            user_id=user_id,
            question=item.get("question"),
            answer=item.get("answer"),
            created_by=user_id,
        )
        db.add(q)

    # Commit status + answers immediately so the questionnaire is always
    # marked "completed" regardless of what happens during PDF upload.
    db.commit()
    db.refresh(claim_questionnaire)

    witness = db.execute(
        text("""
            SELECT cd.first_name, cd.surname, a.email
            FROM client_details cd
            LEFT JOIN addresses a ON cd.address_id = a.id
            WHERE cd.claim_id = :cid
            AND cd.role = 'WITNESS'
            AND cd.is_active = true
            ORDER BY cd.id DESC
            LIMIT 1
        """),
        {"cid": claim_id}
    ).fetchone()

    witness_email = witness.email if witness else None
    final_witness_name = witness_name or (
        f"{witness.first_name} {witness.surname}" if witness else "Witness"
    )

    submission_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5174")

    # Default fallback link if no PDF is uploaded or S3 fails
    view_link = f"{frontend_url}/questionnaire?claim_questionnaire_id={claim_questionnaire.id}"

    pdf_upload = None
    pdf_filename = None
    case_document = None

    # Upload PDF to S3 (non-fatal — status is already committed above)
    if pdf_file:
        try:
            pdf_bytes = await pdf_file.read()

            pdf_filename = pdf_file.filename or f"Witness-Questionnaire-{claim_questionnaire.id}.pdf"

            s3_service = S3Service()

            pdf_upload = s3_service.upload_witness_questionnaire_pdf_bytes(
                pdf_bytes=pdf_bytes,
                claim_id=claim_id,
                filename=pdf_filename,
            )

            filename = pdf_upload["s3_key"].split("/")[-1]
            ext = Path(filename).suffix.lower() or ".pdf"

            case_document = CaseDocument(
                claim_id=claim_id,
                file_name=filename,
                original_filename=pdf_filename,
                file_extension=ext,
                content_type="application/pdf",
                file_size_bytes=len(pdf_bytes),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                category="Witness",
                tag="witness-questionnaire",
                source_type="witness_questionnaire",
                s3_key=pdf_upload["s3_key"],
                file_url=pdf_upload.get("file_url"),
                version=1,
                is_latest=True,
                is_active=True,
                is_deleted=False,
                tenant_id=tenant_id,
                created_by=user_id,
                updated_by=user_id,
                metadata_json={
                    "claim_questionnaire_id": claim_questionnaire.id,
                    "claim_id": claim_id,
                    "case_reference": case_reference,
                    "witness_name": witness_name,
                    "document_role": "witness_questionnaire_pdf",
                    "preview_type": "pdf",
                },
            )

            db.add(case_document)
            db.flush()
            db.refresh(case_document)

            # Generate presigned URL; fall back to default link on failure
            if pdf_upload.get("s3_key"):
                try:
                    view_link = s3_service.generate_presigned_url(
                        s3_key=pdf_upload["s3_key"],
                        expires_in=7 * 24 * 3600,
                    )
                    print("PRESIGNED VIEW LINK:", view_link)
                except Exception as exc:
                    print("Failed to generate presigned URL, using fallback:", exc)
            else:
                print("S3 upload returned no s3_key, using fallback link")

            db.commit()

        except Exception as exc:
            print("Witness PDF upload failed (non-fatal, status already saved):", exc)
            db.rollback()

    activity_payload = {
        "source_type": "witness_questionnaire",
        "title": "Witness Questionnaire Submitted",
        "summary": "Witness questionnaire submitted successfully.",
        "detail_text": witness_statement or "",
        "file_name": pdf_filename or "",
        "file_url": view_link,
        "s3_key": pdf_upload.get("s3_key") if pdf_upload else "",
        "case_document_id": case_document.id if case_document else None,
        "witness_name": witness_name,
        "witness_email": witness_email or "",
    }

    HistoryActivityService.create_activity(
        db=db,
        claim_id=claim_id,
        file_name=f"Witness Questionnaire Submitted for claim {case_reference}",
        file_path=json.dumps(activity_payload),
        file_type=HistoryLogType.WITNESS_QUESTIONNAIRE_SUBMITTED,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    if normalized_status.lower() == "completed" and not questionnaire_was_completed:
        try:
            from appflow.services.notification_service import safe_notify

            safe_notify(
                db,
                recipient_user_id=user_id,
                tenant_id=tenant_id,
                actor_user_id=None,
                category="Claim",
                tab="Claims",
                title="Witness Questionnaire Received",
                description=(
                    f"{final_witness_name} submitted a witness questionnaire "
                    f"for {case_reference}."
                ),
                claim_id=claim_id,
            )
        except Exception:
            pass

    logo_src = f"data:image/png;base64,{logo_encoded}"

    if witness_email:
        witness_email_html = f"""
<html>
<body style="margin:0;padding:0;background-color:#ffffff;font-family:Arial,sans-serif;">
<table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff;">
  <tr><td align="center" style="padding:40px 20px;">

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:640px;margin-bottom:20px;">
      <tr><td align="center">
        <img src="{logo_src}" alt="Nationwide Assist" width="60" style="display:block;border:0;">
      </td></tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:640px;margin-bottom:28px;">
      <tr><td align="center" style="font-size:16px;font-weight:600;color:#111111;padding-bottom:10px;">
        Dear {final_witness_name}
      </td></tr>
      <tr><td align="center" style="font-size:14px;color:#444444;line-height:1.6;">
        Thank you for completing the witness questionnaire.<br/>
        Your submitted witness form has been successfully received.
      </td></tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:320px;margin-bottom:40px;">
      <tr><td align="center" style="font-size:14px;color:#444444;line-height:1.6;padding-bottom:16px;">
        You can view, download, or print the submitted PDF using the link below:
      </td></tr>
      <tr><td align="center">
        <table border="0" cellspacing="0" cellpadding="0">
          <tr><td align="center" bgcolor="#0352FD" style="border-radius:4px;">
            <a href="{view_link}" target="_blank" style="padding:16px 40px;font-size:16px;font-weight:500;color:#ffffff;text-decoration:none;display:inline-block;">
              View Witness Form
            </a>
          </td></tr>
        </table>
      </td></tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:580px;margin-bottom:24px;">
      <tr><td style="height:1px;background-color:#e5e7eb;"></td></tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:580px;">
      <tr><td align="center" style="color:#444444;">
        <span style="font-size:12px;font-weight:600;">Kind regards,</span><br/>
        <span style="font-size:14px;font-weight:600;display:inline-block;margin-top:4px;">Nationwide Assist IT / Systems Team</span>
      </td></tr>
    </table>

  </td></tr>
</table>
</body>
</html>"""

        background_tasks.add_task(
            send_email,
            to_email=witness_email,
            subject="Thank You For Completing Questionnaire",
            html_content=witness_email_html,
        )

    company_email_html = f"""
<html>
<body style="margin:0;padding:0;background-color:#ffffff;font-family:Arial,sans-serif;">
<table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff;">
  <tr><td align="center" style="padding:40px 20px;">

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:640px;margin-bottom:20px;">
      <tr><td align="center">
        <img src="{logo_src}" alt="Nationwide Assist" width="60" style="display:block;border:0;">
      </td></tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:640px;margin-bottom:20px;">
      <tr><td align="center" style="font-size:16px;font-weight:600;color:#111111;padding-bottom:10px;">
        Dear {handler_name}
      </td></tr>
      <tr><td align="center" style="font-size:14px;color:#444444;line-height:1.6;">
        A new witness form has been successfully submitted online. Please find the details below:
      </td></tr>
    </table>

    <table border="0" cellspacing="0" cellpadding="8" style="width:384px;max-width:384px;border:1px solid #e5e7eb;border-radius:8px;background-color:#ffffff;margin-bottom:24px;">
      <tr>
        <td style="color:#444444;font-size:12px;font-weight:400;width:176px;">Case Reference:</td>
        <td style="color:#444444;font-size:12px;font-weight:600;">{case_reference}</td>
      </tr>
      <tr><td colspan="2" style="padding:0 8px;"><div style="height:1px;background-color:#e5e7eb;"></div></td></tr>
      <tr>
        <td style="color:#444444;font-size:12px;font-weight:400;">Witness Name</td>
        <td style="color:#444444;font-size:12px;font-weight:600;">{final_witness_name}</td>
      </tr>
      <tr><td colspan="2" style="padding:0 8px;"><div style="height:1px;background-color:#e5e7eb;"></div></td></tr>
      <tr>
        <td style="color:#444444;font-size:12px;font-weight:400;">Submission Date/Time</td>
        <td style="color:#444444;font-size:12px;font-weight:600;">{submission_time}</td>
      </tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:320px;margin-bottom:40px;">
      <tr><td align="center" style="font-size:14px;color:#444444;line-height:1.6;padding-bottom:16px;">
        You can view the full witness form, download it, or print it using the link below:
      </td></tr>
      <tr><td align="center">
        <table border="0" cellspacing="0" cellpadding="0">
          <tr><td align="center" bgcolor="#0352FD" style="border-radius:4px;">
            <a href="{view_link}" target="_blank" style="padding:16px 40px;font-size:16px;font-weight:500;color:#ffffff;text-decoration:none;display:inline-block;">
              View Witness Form
            </a>
          </td></tr>
        </table>
      </td></tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:580px;margin-bottom:24px;">
      <tr><td style="height:1px;background-color:#e5e7eb;"></td></tr>
    </table>

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:580px;">
      <tr><td align="center" style="color:#444444;">
        <span style="font-size:12px;font-weight:600;">Kind regards,</span><br/>
        <span style="font-size:14px;font-weight:600;display:inline-block;margin-top:4px;">Nationwide Assist IT / Systems Team</span>
      </td></tr>
    </table>

  </td></tr>
</table>
</body>
</html>"""

    background_tasks.add_task(
        send_email,
        to_email="marwanationwideassist@outlook.com",
        subject=f"New Witness Form Submitted - Case Ref: {case_reference}",
        html_content=company_email_html,
    )

    return {
        "status": "success",
        "message": "Questionnaire saved and notifications sent",
        "claim_questionnaire_id": claim_questionnaire.id,
        "case_reference": case_reference,
        "handler_name": handler_name,
        "pdf_url": view_link,
        "case_document_id": case_document.id if case_document else None,
    }

@email_router.get("/get/{claim_questionnaire_id}")
def get_claim_questionnaire(
    claim_questionnaire_id: int,
    db: Session = Depends(get_session)
):
    cq = db.query(ClaimQuestionnaire).filter(ClaimQuestionnaire.id == claim_questionnaire_id).first()
    if not cq:
        raise HTTPException(status_code=404, detail="ClaimQuestionnaire not found")

    questions = db.query(Questionnaire).filter(Questionnaire.claim_questionnaire_id == cq.id).all()
    answers = [{"question": q.question, "answer": q.answer} for q in questions]

    # Find the uploaded PDF case_document for this questionnaire
    case_document_id = None
    pdf_url = None
    try:
        doc = db.execute(
            text("""
                SELECT id, s3_key FROM case_documents
                WHERE source_type = 'witness_questionnaire'
                  AND is_active = true
                  AND is_deleted = false
                  AND metadata_json->>'claim_questionnaire_id' = :cq_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {"cq_id": str(claim_questionnaire_id)}
        ).fetchone()

        if doc:
            case_document_id = doc.id
            if doc.s3_key:
                s3_service = S3Service()
                pdf_url = s3_service.generate_presigned_url(
                    s3_key=doc.s3_key,
                    expires_in=2 * 60 * 60,
                )
    except Exception as exc:
        print(f"Failed to fetch document for questionnaire {claim_questionnaire_id}:", exc)

    return {
        "id": cq.id,
        "claim_id": cq.claim_id,
        "status": cq.status,
        "signWitness": cq.witness_sign,
        "signOfficer": cq.officer_sign,
        "nameWitness": cq.witness_name,
        "nameOfficer": cq.officer_name,
        "dateWitness": cq.date_of_witness,
        "dateOfficer": cq.date_of_officer,
        "answers": answers,
        "case_document_id": case_document_id,
        "pdf_url": pdf_url,
    }


@email_router.put("/update-status/{claim_questionnaire_id}")
def update_claim_questionnaire_status(
    claim_questionnaire_id: int,
    data: UpdateQuestionnaireStatusRequest,
    db: Session = Depends(get_session)
):
    # Fetch the ClaimQuestionnaire
    cq = db.query(ClaimQuestionnaire).filter(ClaimQuestionnaire.id == claim_questionnaire_id).first()
    if not cq:
        raise HTTPException(status_code=404, detail="ClaimQuestionnaire not found")

    # Update the status
    cq.status = data.status
    db.commit()
    db.refresh(cq)

    return {
        "status": "success",
        "message": f"ClaimQuestionnaire status updated to '{cq.status}'",
        "claim_questionnaire_id": cq.id,
        "new_status": cq.status
    }


@email_router.put("/open/{token}")
def mark_questionnaire_opened(
    token: str,
    db: Session = Depends(get_session)
):
    decoded = decode_auth_token(token)
    claim_questionnaire_id = decoded.get("claim_questionnaire_id")

    cq = db.query(ClaimQuestionnaire).filter(
        ClaimQuestionnaire.id == claim_questionnaire_id
    ).first()

    if not cq:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    if cq.status != "completed":
        cq.status = "opened"

    db.commit()

    return {
        "status": "success",
        "questionnaire_status": cq.status,
        "claim_questionnaire_id": cq.id,
    }

@email_router.get("/questionnaire-status/{claim_id}/{witness_id}")
def get_questionnaire_status(
    claim_id: int,
    witness_id: int,
    db: Session = Depends(get_session)
):
    # Prefer a completed/received questionnaire over any later "sent" re-send, so
    # re-sending the link doesn't wipe the "Received" status + View Details CTA.
    record = db.query(ClaimQuestionnaire).filter(
        ClaimQuestionnaire.claim_id == claim_id,
        ClaimQuestionnaire.witness_id == witness_id,
        ClaimQuestionnaire.completed_at.isnot(None),
    ).order_by(ClaimQuestionnaire.id.desc()).first()

    if not record:
        record = db.query(ClaimQuestionnaire).filter(
            ClaimQuestionnaire.claim_id == claim_id,
            ClaimQuestionnaire.witness_id == witness_id
        ).order_by(ClaimQuestionnaire.id.desc()).first()

    if not record:
        return {
            "claim_questionnaire_id": None,
            "status": "not_sent",
            "sent_at": None,
            "opened_at": None,
            "completed_at": None,
            "case_document_id": None,
        }

    # Look up the case_document_id for this questionnaire's PDF
    case_document_id = None
    try:
        doc = db.execute(
            text("""
                SELECT id FROM case_documents
                WHERE source_type = 'witness_questionnaire'
                  AND is_active = true
                  AND is_deleted = false
                  AND metadata_json->>'claim_questionnaire_id' = :cq_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {"cq_id": str(record.id)}
        ).fetchone()
        if doc:
            case_document_id = doc.id
    except Exception as exc:
        print(f"Failed to fetch case_document_id for questionnaire {record.id}:", exc)

    return {
        "claim_questionnaire_id": record.id,
        "status": record.status,
        "sent_at": record.sent_at,
        "opened_at": record.opened_at,
        "completed_at": record.completed_at,
        "case_document_id": case_document_id,
    }


@email_router.post("/demo-questionnaire-link/{claim_id}")
def create_demo_questionnaire_link(
    claim_id: int,
    request: Request,
    db: Session = Depends(get_session),
):
    user_id = actor_id(request)
    tenant_id = get_tenant_id(request)

    claim_questionnaire = ClaimQuestionnaire(
        claim_id=claim_id,
        witness_id=None,
        status="sent",
        witness_name="Demo Witness",
        created_by=user_id,
        sent_at=datetime.utcnow(),
    )

    db.add(claim_questionnaire)
    db.flush()

    token = generate_deep_link_token(
        request=request,
        claim_id=claim_id,
        witness_id=0,
        claim_questionnaire_id=claim_questionnaire.id,
    )

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5174")
    link = f"{frontend_url}/questionnaire/{token}/step-1"

    HistoryActivityService.create_activity(
        db=db,
        claim_id=claim_id,
        file_name=f"Demo witness questionnaire link created",
        file_path=link,
        file_type=HistoryLogType.WITNESS_LINK_SEND,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    db.commit()
    db.refresh(claim_questionnaire)

    return {
        "status": "success",
        "claim_questionnaire_id": claim_questionnaire.id,
        "deep_link": link,
    }
