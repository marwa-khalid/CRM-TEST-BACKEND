import base64
import io
import os
import time
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request,BackgroundTasks
from pydantic import BaseModel
from jinja2 import Template
from libdata.settings import get_session
from libauth.token_util import sign_jwt,decode_auth_token
from appflow.utils import actor_id, get_tenant_id
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from sqlalchemy.orm import Session
from weasyprint import HTML
from dotenv import load_dotenv
from appflow.models.witness import WitnessEmailRequest, QuestionnaireSubmitRequest, UpdateQuestionnaireStatusRequest
from libdata.models.tables import Questionnaire, ClaimQuestionnaire
from fastapi.responses import FileResponse, StreamingResponse
from sendgrid.helpers.mail import Mail, TrackingSettings, ClickTracking
from sendgrid.helpers.mail import Mail, To, ReplyTo

load_dotenv()

email_router = APIRouter(prefix="/witnesses", tags=["Witnesses Email"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")


# --- helper to render HTML -> PDF ---
def render_pdf_from_html(template_str: str, context: dict) -> bytes:
    template = Template(template_str)
    rendered_html = template.render(**context)
    pdf_io = io.BytesIO()
    HTML(string=rendered_html).write_pdf(pdf_io)
    return pdf_io.getvalue()


# --- deep link token generator ---
def generate_deep_link_token(request: Request, claim_id: int) -> str:
    user_id = actor_id(request)
    tenant_id = get_tenant_id(request)
    issue_time = datetime.utcnow()
    expiry_time = issue_time + timedelta(weeks=1)
    token_payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "iat": int(time.mktime(issue_time.timetuple())),
        "exp": int(time.mktime(expiry_time.timetuple())),
        "type": "deep_link",
        "claim_id": claim_id
    }
    token = sign_jwt(token_payload)

    # if sign_jwt returns dict, extract access_token
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
    # 1. fetch client details
    client = db.execute(
        """
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
        """,
        {"cid": claim_id}
    ).fetchone()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # 2. prepare context
    client_detail = {
        "reference": data.reference,
        "name": f"{client.first_name} {client.surname}",
        "address": client.address or "",
        "dob": client.date_of_birth.strftime("%d-%m-%Y") if client.date_of_birth else "",
        "occupation": client.occupation or "",
        "date": datetime.now().strftime("%d-%m-%Y"),
        "witness_name": data.witness_name,
        "witness_date": datetime.now().strftime("%d-%m-%Y"),
        "accident_time": client.accident_time.strftime("%d-%m-%Y %H:%M") if client.accident_time else "",
        "accident_location": client.accident_location or "",
        "handler_name": client.handler_name or "",
    }

    result = {
        "claim_id": claim_id,
        "option": data.option,
        "client_detail": client_detail
    }

    # 3. Build response depending on option
    if data.option == "pdf":
        with open(os.path.join(TEMPLATE_DIR, "letter.html"), "r", encoding="utf-8") as f:
            letter_template = f.read()
        with open(os.path.join(TEMPLATE_DIR, "questionnaire.html"), "r", encoding="utf-8") as f:
            questionnaire_template = f.read()

        questionnaire_pdf = render_pdf_from_html(questionnaire_template, client_detail)
        letter_pdf = render_pdf_from_html(letter_template, client_detail)

        questionnaire_encoded = base64.b64encode(questionnaire_pdf).decode()
        letter_encoded = base64.b64encode(letter_pdf).decode()

        claim = db.execute(
            """
            SELECT c.id, c.file_opened_at, cd.surname AS client_surname
            FROM claims c
            JOIN client_details cd ON cd.claim_id = c.id AND cd.role = 'CLIENT'
            WHERE c.id = :cid
            """,
            {"cid": claim_id}
        ).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        year_month = datetime.now().strftime("%Y%m")
        case_reference = f"{client.surname}-{year_month}-{claim.id:04d}"
        # Format: 02-12-26 / 5:35 PM
        submission_time = datetime.now().strftime("%d-%m-%y / %I:%M %p")

        # Case Reference: 202602-0015

        logo_url = "https://image2url.com/r2/default/images/1772144213817-5641d8a2-de81-4933-b96d-838f8644d636.svg"
        # Note: Swap for a PNG for better email compatibility if possible.
        message = Mail(
            from_email="No-Reply <noreplynationwideassist@yopmail.com",
            to_emails=data.witness_email,
            subject=f"Witness Questionnaire - Case Ref: {case_reference}",
            html_content=f"""
                                        <html>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: Arial, sans-serif;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                
                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 30px;">
                    <tr>
                        <td align="center">
                            <img src="{logo_url}" alt="Nationwide Assist" width="200" style="display: block; border: 0;">
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
                            A new witness form has been successfully submitted online.<br/>
                            Please find the details below:
                        </td>
                    </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="16" style="max-width: 420px; border: 1px solid #CCCCCC; border-radius: 8px; background-color: #ffffff;">
                    <tr>
                        <td>
                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td width="160" style="color: #444444; font-size: 12px; font-weight: 400;">Case Reference:</td>
                                    <td style="color: #444444; font-size: 12px; font-weight: 600;">{case_reference}</td>
                                </tr>
                                <tr><td colspan="2" style="padding: 8px 0;"><div style="height: 1px; background-color: #CCCCCC;"></div></td></tr>
                                
                                <tr>
                                    <td width="160" style="color: #444444; font-size: 12px; font-weight: 400;">Witness Name</td>
                                    <td style="color: #444444; font-size: 12px; font-weight: 600;">{data.witness_name}</td>
                                </tr>
                                <tr><td colspan="2" style="padding: 8px 0;"><div style="height: 1px; background-color: #CCCCCC;"></div></td></tr>
                                
                                <tr>
                                    <td width="160" style="color: #444444; font-size: 12px; font-weight: 400;">Submission Date/Time</td>
                                    <td style="color: #444444; font-size: 12px; font-weight: 600;">{submission_time}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>

                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 380px; margin-top: 30px;">
                    <tr>
                        <td align="center" style="padding-bottom: 20px; font-size: 14px; color: #444444;">
                            You can view the full witness form, download it, or print it using the link below:
                        </td>
                    </tr>
                    <tr>
                        <td align="center">
                            <table border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td align="center" bgcolor="#0352FD" style="border-radius: 4px;">
                                        <a href="" target="_blank" style="padding: 16px 40px; font-size: 16px; font-weight: 500; color: #ffffff; text-decoration: none; display: inline-block;">
                                            View Witness Form
                                        </a>
                                    </td>
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
                                    """)
        message.attachment = [
            Attachment(
                FileContent(questionnaire_encoded),
                FileName("questionnaire.pdf"),
                FileType("application/pdf"),
                Disposition("attachment")
            ),
            Attachment(
                FileContent(letter_encoded),
                FileName("letter.pdf"),
                FileType("application/pdf"),
                Disposition("attachment")
            )
        ]

        # send
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        print("working")
        print(message)

        sg.send(message)
        return {"status": "success"}

    # --- Option 2: Secure Link ---
    elif data.option == "link":
        # Generate secure digital link
        token = generate_deep_link_token(request, claim_id)
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5174")
        link = f"{frontend_url}/questionnaire?details={token}&claim_id={claim_id}"

        result.update({
            "link": link,
            "message": "Secure link generated (would have been sent via email)"
        })

    elif data.option == "download":
        with open(os.path.join(TEMPLATE_DIR, "letter.html"), "r", encoding="utf-8") as f:
            letter_template = f.read()
        with open(os.path.join(TEMPLATE_DIR, "questionnaire.html"), "r", encoding="utf-8") as f:
            questionnaire_template = f.read()

        questionnaire_pdf = render_pdf_from_html(questionnaire_template, client_detail)
        letter_pdf = render_pdf_from_html(letter_template, client_detail)

        # create a zip with both PDFs
        import zipfile
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, mode="w") as zipf:
            zipf.writestr("questionnaire.pdf", questionnaire_pdf)
            zipf.writestr("letter.pdf", letter_pdf)
        zip_io.seek(0)

        # Encode zip to base64
        zip_base64 = base64.b64encode(zip_io.read()).decode()

        result.update({
            "zip_base64": zip_base64,
            "filename": "documents.zip",
            "message": "Zip file generated and returned to frontend"
        })
        return result

    else:
        raise HTTPException(status_code=400, detail="Invalid option selected")

    return result


# --- helper to send emails via SendGrid ---
def send_email(to_email: str, subject: str, html_content: str):
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="SendGrid API key not set in environment")
    sg = SendGridAPIClient(api_key)
    message = Mail(
        from_email="No-Reply <noreplynationwideassist@yopmail.com",  # ✅ replace with your verified sender in SendGrid
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )
    message.reply_to = ReplyTo("noreplynationwideassist@yopmail.com", "No-Reply")
    print(os.getenv("SENDGRID_API_KEY"))
    tracking_settings = TrackingSettings()
    tracking_settings.click_tracking = ClickTracking(enable=False, enable_text=False)
    message.tracking_settings = tracking_settings
    sg.send(message)

@email_router.post("/save")
def save_questionnaire_by_link(
    data: QuestionnaireSubmitRequest,
    token: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session)
):
    # Decode token
    decoded = decode_auth_token(token)
    claim_id = decoded.get("claim_id")
    user_id = decoded.get("user_id")
    exp = decoded.get("exp")

    if not claim_id or not user_id:
        raise HTTPException(status_code=400, detail="Invalid token")
    if datetime.utcfromtimestamp(exp) < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Token expired")

    # ✅ Create ClaimQuestionnaire
    claim_questionnaire = ClaimQuestionnaire(
        claim_id=claim_id,
        status=data.status,
        witness_sign=data.witness_sign,
        officer_sign=data.officer_sign,
        witness_name=data.witness_name,
        officer_name=data.officer_name,
        date_of_witness=data.date_of_witness,
        date_of_officer=data.date_of_officer,
        created_by=user_id,
    )
    db.add(claim_questionnaire)
    db.flush()

    for item in data.answers:
        q = Questionnaire(
            claim_questionnaire_id=claim_questionnaire.id,
            user_id=user_id,
            question=item.question,
            answer=item.answer,
            created_by=user_id,
        )
        db.add(q)

    db.commit()
    db.refresh(claim_questionnaire)

    # ✅ Lookup witness email
    witness = db.execute(
        """
        SELECT cd.first_name, cd.surname, a.email
        FROM client_details cd
        LEFT JOIN addresses a ON cd.address_id = a.id
        WHERE cd.claim_id = :cid AND cd.role = 'WITNESS' AND cd.is_active = true
        ORDER BY cd.id DESC LIMIT 1
        """,
        {"cid": claim_id}
    ).fetchone()

    if not witness or not witness.email:
        raise HTTPException(status_code=404, detail="Witness email not found")

    witness_email = witness.email
    witness_name = data.witness_name or (witness.first_name + " " + witness.surname)

    # ✅ Fetch claim + handler + client surname for case reference
    claim = db.execute(
        """
        SELECT c.id, c.file_opened_at, h.label AS handler_name, cd.surname AS client_surname
        FROM claims c
        LEFT JOIN handlers h ON h.id = c.handler_id
        JOIN client_details cd ON cd.claim_id = c.id AND cd.role = 'CLIENT'
        WHERE c.id = :cid
        """,
        {"cid": claim_id}
    ).fetchone()

    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    # Build case reference
    year = claim.file_opened_at.strftime("%Y")
    month = claim.file_opened_at.strftime("%m")
    padded_id = str(claim.id).zfill(5)  # ensures 00001, 00123, 01000, etc.
    case_reference = f"{claim.client_surname}-{year}{month}-{padded_id}"

    handler_name = claim.handler_name or "Claim Handler"

    # --- Send Emails ---
    submission_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    # ✅ Witness Confirmation
    witness_email_html = f"""
        <p>Dear {witness_name},</p>
        <p>Thank you for completing the witness questionnaire. Your response has been successfully submitted.</p>
        <p>Submission Date/Time: {submission_time}</p>
        <br>
        <p>Best Regards,<br>Nationwide Assist Team</p>
    """
    background_tasks.add_task(
        send_email,
        to_email=witness_email,
        subject="Thank You For Completing Questionnaire",
        html_content=witness_email_html,
    )

    # ✅ Company Notification
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    link = f'<div style="text-align: center;"><a href="{frontend_url}/questionnaire?claim_questionnaire_id={claim_questionnaire.id}" target="_blank" style="background-color:#9e77ed;color:#fff;padding:15px 25px;text-decoration:none;border-radius:5px;cursor:pointer">View Witness Form</a></div>'

    company_email_html = f"""
        <p>Dear {handler_name},</p>
        <p>A new witness form has been successfully submitted online. Please find the details below:</p>
        <ul>
            <li><strong>Case Reference:</strong> {case_reference}</li>
            <li><strong>Witness Name:</strong> {witness_name}</li>
            <li><strong>Submission Date/Time:</strong> {submission_time}</li>
        </ul>
        
        <p>You can view the full witness form, download it, or print it using the link below:</p>
        <br><br>{link}
        <br>
        <p>Best Regards,<br>Nationwide Assist Team</p>
    """
    background_tasks.add_task(
        send_email,
        to_email="usaleem651@gmail.com",
        subject=f"New Witness Form Submitted - Case Ref: {case_reference}",
        html_content=company_email_html,
    )

    return {
        "status": "success",
        "message": "Questionnaire saved and notifications sent",
        "claim_questionnaire_id": claim_questionnaire.id,
        "case_reference": case_reference,
        "handler_name": handler_name,
    }


@email_router.get("/get/{claim_questionnaire_id}")
def get_claim_questionnaire(
    claim_questionnaire_id: int,
    db: Session = Depends(get_session)
):
    # Fetch the ClaimQuestionnaire
    cq = db.query(ClaimQuestionnaire).filter(ClaimQuestionnaire.id == claim_questionnaire_id).first()
    if not cq:
        raise HTTPException(status_code=404, detail="ClaimQuestionnaire not found")

    # Fetch associated Questionnaires
    questions = db.query(Questionnaire).filter(Questionnaire.claim_questionnaire_id == cq.id).all()

    # Serialize Questionnaires
    answers = [{"question": q.question, "answer": q.answer} for q in questions]

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
        "answers": answers
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
