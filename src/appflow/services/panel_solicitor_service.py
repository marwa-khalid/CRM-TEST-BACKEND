import base64
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from libdata.models.tables import PanelSolicitor, Claim, Address,ClientDetail
from appflow.models.panel_solicitor import PanelSolicitorIn
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
from datetime import date
from appflow.services.history_activity_service import HistoryActivityService
from libdata.enums import HistoryLogType
from appflow.utils import build_case_reference

class PanelSolicitorService:

    @staticmethod
    def get_solicitor_by_claim_id(claim_id: int, db: Session):
        existing = db.query(PanelSolicitor).options(
            joinedload(PanelSolicitor.address)
        ).filter(PanelSolicitor.claim_id == claim_id).first()

        if not existing:
            raise HTTPException(status_code=404, detail="Panel solicitor not found")
        return existing

    @staticmethod
    def get_solicitor_by_company_name(company_name: str, db: Session):
        existing = db.query(PanelSolicitor).options(
            joinedload(PanelSolicitor.address)
        ).filter(PanelSolicitor.company_name == company_name).first()

        if not existing:
            raise HTTPException(status_code=404, detail="Panel solicitor not found")
        return existing

    @staticmethod
    def create_solicitor(
            solicitor: PanelSolicitorIn,
            db: Session,
            tenant_id: int,
            current_user_id: int,
            send_email: bool = False,
            send_acceptance_email: bool = False
    ):
        claim = db.query(Claim).filter(
            Claim.id == solicitor.claim_id,
            # Claim.tenant_id == tenant_id
        ).first()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")

        try:
            solicitor_data = solicitor.dict()
            address_data = solicitor_data.pop("address", None)

            address = None
            if address_data:
                address = Address(**address_data,created_by=current_user_id,updated_by=current_user_id)
                db.add(address)
                db.flush()
                solicitor_data["address_id"] = address.id

            new_solicitor = PanelSolicitor(
                **solicitor_data,
                tenant_id=tenant_id,
                created_by=current_user_id,
                updated_by=current_user_id
            )

            # Email service
            email_service = PanelSolicitorEmailService(db, tenant_id)

            if send_acceptance_email:
                # send acceptance email
                email_service.send_acceptance_email(
                    claim_id=new_solicitor.claim_id,
                    solicitor_email=address.email if address else None,
                    solicitor_name=new_solicitor.company_name,
                    recommendation_date=new_solicitor.recommendation_sent or date.today()
                )
                new_solicitor.accepted_sent_date = date.today()
                new_solicitor.email_sent_date = None  # clear email_sent_date
            elif send_email:
                # send regular email
                email_service.send_email(
                    claim_id=new_solicitor.claim_id,
                    solicitor_email=address.email if address else None,
                    company_name=new_solicitor.company_name
                )
                new_solicitor.email_sent_date = date.today()
                new_solicitor.accepted_sent_date = None  # clear accepted_sent_date
            elif solicitor.accepted_sent_date:
                new_solicitor.accepted_sent_date = solicitor.accepted_sent_date
                new_solicitor.email_sent_date = None
            elif solicitor.email_sent_date:
                new_solicitor.email_sent_date = solicitor.email_sent_date
                new_solicitor.accepted_sent_date = None

            db.add(new_solicitor)
            db.commit()
            db.refresh(new_solicitor)
            reference = build_case_reference(claim.id,db)
            HistoryActivityService.create_activity(
                db=db,
                claim_id=claim.id,
                file_name=f"The panel solicitor detail has been created for claim {reference}",
                file_path="",
                file_type=HistoryLogType.CREATED_SOLICITOR_DETAIL,
                user_id=current_user_id,
                tenant_id=tenant_id
            )

            return db.query(PanelSolicitor).options(
                joinedload(PanelSolicitor.address)
            ).filter(PanelSolicitor.id == new_solicitor.id).first()

        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Error creating panel solicitor: {str(e)}"
            )

    @staticmethod
    def update_solicitor(
            claim_id: int,
            solicitor: PanelSolicitorIn,
            db: Session,
            tenant_id: int,
            current_user_id: int,
            send_email: bool = False,
            send_acceptance_email: bool = False
    ):
        # --- Fetch existing solicitor with eager-loaded address ---
        existing = db.query(PanelSolicitor).options(
            joinedload(PanelSolicitor.address)
        ).filter(
            PanelSolicitor.claim_id == claim_id,
            # Claim.tenant_id == tenant_id
        ).join(Claim).first()

        if not existing:
            raise HTTPException(status_code=404, detail="Panel solicitor not found")

        changed_fields = []

        try:
            # --- Extract fields from request ---
            solicitor_data = solicitor.dict(exclude_unset=True, exclude={"address"})
            address_data = getattr(solicitor, "address", None)
            if address_data:
                address_data = address_data.dict(exclude_unset=True)

            # --- Map field labels for history ---
            field_label_map = {
                "company_name": "Company Name",
                "reference": "Reference",
                "recommendation_sent": "Recommendation Sent On",
                "email_sent_date": "Email Sent Date",
                "accepted_sent_date": "Accepted Sent Date",
                "note":"Note",
            }

            address_field_map = {
                "address": "Address",
                "postcode": "Postcode",
                "mobile_tel": "Telephone Main",
                "home_tel": "Home Tel",
                "email": "Email",
            }

            # --- Update main solicitor fields ---
            for key, new_value in solicitor_data.items():
                old_value = getattr(existing, key)
                if new_value != old_value:
                    changed_fields.append(field_label_map.get(key, key))
                    setattr(existing, key, new_value)

            # --- Update address ---
            if address_data:
                if existing.address:
                    # Ensure session tracks the address object
                    db.add(existing.address)
                    for key, new_value in address_data.items():
                        old_value = getattr(existing.address, key)
                        if new_value != old_value:
                            changed_fields.append(f"{address_field_map.get(key, key)}")
                            setattr(existing.address, key, new_value)
                else:
                    # Create new address
                    new_address = Address(**address_data)
                    db.add(new_address)
                    db.flush()  # assign ID
                    existing.address_id = new_address.id
                    changed_fields.append("Address (new)")

            # --- Email service handling ---
            email_service = PanelSolicitorEmailService(db, tenant_id)

            if send_acceptance_email:
                email_service.send_acceptance_email(
                    claim_id=existing.claim_id,
                    solicitor_email=existing.address.email if existing.address else None,
                    solicitor_name=existing.company_name,
                    recommendation_date=existing.recommendation_sent or date.today(),
                )
                existing.accepted_sent_date = date.today()
                changed_fields.append("Accepted Sent Date")

            elif send_email:
                email_service.send_email(
                    claim_id=existing.claim_id,
                    solicitor_email=existing.address.email if existing.address else None,
                    company_name=existing.company_name,
                )
                existing.email_sent_date = date.today()
                changed_fields.append("Email Sent Date")

            # --- Optional explicit date updates from request ---
            if solicitor.accepted_sent_date and solicitor.accepted_sent_date != existing.accepted_sent_date:
                existing.accepted_sent_date = solicitor.accepted_sent_date
                changed_fields.append("Accepted Sent Date")

            if solicitor.email_sent_date and solicitor.email_sent_date != existing.email_sent_date:
                existing.email_sent_date = solicitor.email_sent_date
                changed_fields.append("Email Sent Date")

            # --- Commit updates ---
            existing.updated_by = current_user_id
            db.commit()
            db.refresh(existing)

            # --- Create history activity ---
            if changed_fields:
                file_path = ", ".join(changed_fields)
                reference = build_case_reference(claim_id, db)
                HistoryActivityService.create_activity(
                    db=db,
                    claim_id=claim_id,
                    file_name=f"The panel solicitor detail has been updated for claim {reference}",
                    file_path=file_path,
                    file_type=HistoryLogType.UPDATED_SOLICITOR_DETAIL,
                    user_id=current_user_id,
                    tenant_id=tenant_id
                )

            # --- Return updated solicitor with address ---
            return db.query(PanelSolicitor).options(
                joinedload(PanelSolicitor.address)
            ).filter(PanelSolicitor.id == existing.id).first()

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error updating panel solicitor: {str(e)}")

    @staticmethod
    def deactivate_solicitor(solicitor_id: int, db: Session, tenant_id: int):
        solicitor_to_deactivate = db.query(PanelSolicitor).filter(
            PanelSolicitor.id == solicitor_id,
            # Claim.tenant_id == tenant_id
        ).join(Claim).first()

        if not solicitor_to_deactivate:
            raise HTTPException(status_code=404, detail="Panel solicitor not found")

        try:
            solicitor_to_deactivate.is_active = False
            db.commit()
            db.refresh(solicitor_to_deactivate)
            return {"detail": "Panel solicitor deactivated successfully"}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error deactivating panel solicitor: {str(e)}")

    @staticmethod
    def search_solicitors(query: str, db: Session, tenant_id: int):
        return db.query(PanelSolicitor).options(
            joinedload(PanelSolicitor.address)
        ).filter(
            PanelSolicitor.company_name.ilike(f"%{query}%"),
            # Claim.tenant_id == tenant_id
        ).join(Claim).all()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logo_path = os.path.join(BASE_DIR, "static", "logo.png")
with open(logo_path, "rb") as f:
    logo_encoded = base64.b64encode(f.read()).decode()


class PanelSolicitorEmailService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def _get_logo_attachment(self) -> Attachment:
        attachment = Attachment()
        attachment.file_content = FileContent(logo_encoded)
        attachment.file_type = FileType("image/png")
        attachment.file_name = FileName("logo.png")
        attachment.disposition = Disposition("inline")
        attachment.content_id = ContentId("companylogo")
        return attachment

    def _build_email_html(self, company_name: str, case_reference: str) -> str:
        """Return HTML string for solicitor email"""
        return f"""
        <html>
          <head>
            <style>
              body {{ font-family: 'Inter'; margin:0; padding:0; }}ul {{margin: 0;padding: 0;}}
              .header {{ padding:15px; text-align:left; border-bottom:1px solid #ddd; }}
              .footer {{ padding:15px; text-align:left; border-top:1px solid #ddd; font-size:12px; color:black; }}
            </style>
          </head>
          <body>
            <!-- Header -->
            <div class="header">
              <img src="cid:companylogo" alt="ProClaim" width="40" style="vertical-align: middle; margin-right: 8px;" />
              <span style="font-size:20px; font-weight:bold; vertical-align: middle;">ProClaim</span>
            </div>

            <!-- Body -->
            <div style="padding:20px;">
              <p><strong>Dear {company_name},</strong></p>
              <p>Please find details for the claim:</p>
              <ul>
                <li>Case Reference: {case_reference}</li>
                <li>Company Name: {company_name}</li>
              </ul>
              <p>Regards,<br><strong>Nationwide Assist Team</strong></p>
            </div>

            <!-- Footer -->
            <div class="footer">
              <p>This email was sent to claim@nationwideassist.co.uk. If you'd rather not receive this kind of email, you can unsubscribe or manage your email preferences.<br>
              <img src="cid:companylogo" alt="ProClaim" width="25" style="vertical-align: middle; margin-right: 6px;" />
              <span style="font-size:13px; font-weight:bold; vertical-align: middle;">ProClaim</span>
              </p>
            </div>
          </body>
        </html>
        """

    def _fetch_claim(self, claim_id: int):
        claim_with_client = (
            self.db.query(Claim, ClientDetail.surname.label("client_surname"))
            .join(ClientDetail, ClientDetail.claim_id == Claim.id)
            .filter(
                Claim.id == claim_id,
                Claim.tenant_id == self.tenant_id
            )
            .first()
        )

        if not claim_with_client:
            raise HTTPException(status_code=404, detail="Claim or client not found")

        claim, client_surname = claim_with_client
        claim.client_surname = client_surname
        return claim

    def _build_case_reference(self, claim) -> str:
        year = claim.file_opened_at.strftime("%Y")
        month = claim.file_opened_at.strftime("%m")
        padded_id = str(claim.id).zfill(5)
        return f"{claim.client_surname}-{year}{month}-{padded_id}"

    def send_email(self, claim_id: int, solicitor_email: str, company_name: str,current_user=int):
        # 1. fetch claim
        claim = self._fetch_claim(claim_id)
        # 2. build case reference
        case_reference = self._build_case_reference(claim)
        # 3. build html
        html_content = self._build_email_html(company_name, case_reference)
        # 4. build email message
        # 4/5. Graph-first so it reaches Outlook (logo auto-attached via
        # cid:companylogo); SendGrid fallback.
        from appflow.services.email_delivery import send_email as deliver_email
        deliver_email(
            to=solicitor_email,
            subject=f"Signed Documents - Case Ref: {case_reference}",
            html=html_content,
        )
        reference = build_case_reference(claim_id,self.db)
        HistoryActivityService.create_activity(
            db=self.db,
            claim_id=claim_id,
            file_name=f"The panel solicitor singed documents sent for claim {reference}",
            file_path="",
            file_type=HistoryLogType.SOLICITOR_DOCUMENT_SEND,
            user_id=current_user,
            tenant_id=self.tenant_id
        )
        return case_reference

    def _build_acceptance_email_html(self, solicitor_name: str, case_reference: str, recommendation_date: str) -> str:
        """Return HTML string for claim acceptance email"""
        return f"""
        <html>
          <head>
            <style>
              body {{ font-family: 'Inter'; margin:0; padding:0; }} ul {{ margin:0; padding:0; }}
              .header {{ padding:15px; text-align:left; border-bottom:1px solid #ddd; }}
              .footer {{ padding:15px; text-align:left; border-top:1px solid #ddd; font-size:12px; color:black; }}
            </style>
          </head>
          <body>
            <div class="header">
              <img src="cid:companylogo" alt="ProClaim" width="40" style="vertical-align: middle; margin-right: 8px;" />
              <span style="font-size:20px; font-weight:bold; vertical-align: middle;">ProClaim</span>
            </div>

            <div style="padding:20px;">
              <p><strong>Dear {solicitor_name},</strong></p>
              <p>The following claim has been accepted:</p>
              <ul>
                <li>Case Reference: {case_reference}</li>
                <li>Company Name: {solicitor_name}</li>
                <li>Recommendation Sent Date: {recommendation_date}</li>
              </ul>
              <p>Regards,<br><strong>Nationwide Assist Team</strong></p>
            </div>

            <div class="footer">
              <p>This email was sent to claim@nationwideassist.co.uk. If you'd rather not receive this kind of email, you can unsubscribe or manage your email preferences.<br>
              <img src="cid:companylogo" alt="ProClaim" width="25" style="vertical-align: middle; margin-right: 6px;" />
              <span style="font-size:13px; font-weight:bold; vertical-align: middle;">ProClaim</span>
              </p>
            </div>
          </body>
        </html>
        """

    def send_acceptance_email(self, claim_id: int, solicitor_email: str, solicitor_name: str,
                              recommendation_date: date,current_user:int):
        # 1. fetch claim
        claim = self._fetch_claim(claim_id)
        # 2. build case reference
        case_reference = self._build_case_reference(claim)
        # 3. build html
        html_content = self._build_acceptance_email_html(
            solicitor_name=solicitor_name,
            case_reference=case_reference,
            recommendation_date=recommendation_date.strftime("%d-%m-%Y")
        )
        # 4/5. Graph-first so it reaches Outlook (logo auto-attached via
        # cid:companylogo); SendGrid fallback.
        from appflow.services.email_delivery import send_email as deliver_email
        deliver_email(
            to=solicitor_email,
            subject=f"Claim Accepted – Case Ref: {case_reference}",
            html=html_content,
        )
        reference = build_case_reference(claim_id,self.db)
        HistoryActivityService.create_activity(
            db=self.db,
            claim_id=claim_id,
            file_name=f"The panel solicitor acceptance sent for claim {reference}",
            file_path="",
            file_type=HistoryLogType.SOLICITOR_ACCEPTED_SEND,
            user_id=current_user,
            tenant_id=self.tenant_id
        )
        return case_reference