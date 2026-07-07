import os
import base64
import io
import requests
from typing import Optional
from fastapi import HTTPException
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId
from sqlalchemy.orm import Session, joinedload
from jinja2 import Template
from weasyprint import HTML
from appflow.services.vehicle_detail import get_comprehensive_vehicle_damage_report
from appflow.models.vehicle_detail import ComprehensiveVehicleDamageReport
from appflow.utils import get_full_url
from libdata.models.tables import (
    VehicleDetail,
    ThirdPartyVehicle,
    VehicleDamageAIReport,
    VehicleDamageAIImage,
    Claim,
    User,
)


class VehicleDamageReportEmailService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def _get_logo_attachment(self) -> Attachment:
        """Get the company logo attachment for email"""
        logo_path = os.path.join(os.path.dirname(__file__), "..", "static", "logo.png")
        with open(logo_path, "rb") as f:
            logo_encoded = base64.b64encode(f.read()).decode()
        
        return Attachment(
            FileContent(logo_encoded),
            FileName("logo.png"),
            FileType("image/png"),
            Disposition("inline"),
            ContentId("companylogo")
        )

    def _download_and_prepare_image_attachment(self, image_url: str, original_filename: str, index: int) -> Optional[Attachment]:
        """Download image from Cloudinary URL and prepare as email attachment"""
        try:
            # Download image from URL
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Encode image content
            image_encoded = base64.b64encode(response.content).decode()
            
            # Determine content type from response or filename
            content_type = response.headers.get('content-type', 'image/jpeg')
            
            # Create safe filename
            if original_filename:
                safe_filename = original_filename
            else:
                # Extract extension from content type or default to jpg
                ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
                safe_filename = f"vehicle_damage_image_{index}.{ext}"
            
            # Create attachment
            return Attachment(
                FileContent(image_encoded),
                FileName(safe_filename),
                FileType(content_type),
                Disposition("attachment")
            )
        except Exception as e:
            print(f"Error downloading image from {image_url}: {str(e)}")
            return None

    def _build_email_html(self, report_data: ComprehensiveVehicleDamageReport, recipient_name: str = "Recipient") -> str:
        """Build HTML email content for damage report"""
        
        # Format vehicle details
        vehicle_info = f"{report_data.vehicle_details.make_model} ({report_data.vehicle_details.vehicle_reg_no})"
        
        # Format damage summary
        damage_summary = ""
        if report_data.detected_damages.area_of_damage:
            damage_summary = f"<strong>Damage Area:</strong> {report_data.detected_damages.area_of_damage}<br>"
        if report_data.detected_damages.type_of_damage:
            damage_summary += f"<strong>Damage Type:</strong> {report_data.detected_damages.type_of_damage}<br>"
        if report_data.detected_damages.severity:
            damage_summary += f"<strong>Severity:</strong> {report_data.detected_damages.severity}<br>"
        if report_data.detected_damages.confidence_percent:
            damage_summary += f"<strong>Confidence:</strong> {report_data.detected_damages.confidence_percent}%<br>"
        
        # Format AI suggestions
        ai_suggestions = report_data.detected_damages.ai_suggested_actions or "Manual assessment required"
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Vehicle Damage Report</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                .content {{
                    background-color: #ffffff;
                    padding: 20px;
                    border: 1px solid #e9ecef;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .footer {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    font-size: 12px;
                    color: #6c757d;
                    text-align: center;
                }}
                .damage-info {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    border-radius: 4px;
                    padding: 15px;
                    margin: 15px 0;
                }}
                .vehicle-info {{
                    background-color: #d1ecf1;
                    border: 1px solid #bee5eb;
                    border-radius: 4px;
                    padding: 15px;
                    margin: 15px 0;
                }}
                .ai-suggestions {{
                    background-color: #d4edda;
                    border: 1px solid #c3e6cb;
                    border-radius: 4px;
                    padding: 15px;
                    margin: 15px 0;
                }}
                .report-details {{
                    font-size: 14px;
                    color: #6c757d;
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <img src="cid:companylogo" alt="ProClaim" width="40" style="vertical-align: middle; margin-right: 8px;" />
                <span style="font-size:20px; font-weight:bold; vertical-align: middle;">ProClaim</span>
            </div>

            <div class="content">
                <p><strong>Dear {recipient_name},</strong></p>
                
                <p>Please find attached the comprehensive vehicle damage report for the following claim:</p>
                
                <div class="report-details">
                    <strong>Report ID:</strong> {report_data.report_details.report_id}<br>
                    <strong>Claim ID:</strong> {report_data.report_details.claim_id}<br>
                    <strong>Generated On:</strong> {report_data.report_details.generated_on}
                </div>

                <div class="vehicle-info">
                    <h3 style="margin-top: 0;">Vehicle Information</h3>
                    <p><strong>Vehicle:</strong> {vehicle_info}</p>
                    <p><strong>Color:</strong> {report_data.vehicle_details.color}</p>
                    <p><strong>Status:</strong> {report_data.client_vehicle_status}</p>
                </div>

                <div class="damage-info">
                    <h3 style="margin-top: 0;">Damage Assessment</h3>
                    {damage_summary}
                    <p><strong>Total Damaged Points:</strong> {report_data.detected_damages.total_damaged_points_identified}</p>
                    {f'<p><strong>Unrelated Damage:</strong> {report_data.client_unrelated_damage}</p>' if report_data.client_unrelated_damage else ''}
                </div>

                <div class="ai-suggestions">
                    <h3 style="margin-top: 0;">AI Recommendations</h3>
                    <p>{ai_suggestions}</p>
                </div>

                <p>The detailed report with images and technical analysis is attached to this email.</p>
                
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

    def _generate_pdf_report(self, report_data: ComprehensiveVehicleDamageReport) -> bytes:
        """Generate PDF report from the damage report data using weasyprint"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Vehicle Damage Report - {report_data.report_details.report_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }}
                .section {{ margin-bottom: 25px; }}
                .section h2 {{ color: #333; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
                .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
                .damage-details {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; }}
                .ai-analysis {{ background-color: #e8f5e8; padding: 15px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Vehicle Damage Report</h1>
                <p><strong>Report ID:</strong> {report_data.report_details.report_id} | <strong>Claim ID:</strong> {report_data.report_details.claim_id}</p>
                <p><strong>Generated:</strong> {report_data.report_details.generated_on}</p>
            </div>

            <div class="section">
                <h2>Vehicle Information</h2>
                <div class="info-grid">
                    <div>
                        <p><strong>Registration:</strong> {report_data.vehicle_details.vehicle_reg_no}</p>
                        <p><strong>Make & Model:</strong> {report_data.vehicle_details.make_model}</p>
                        <p><strong>Color:</strong> {report_data.vehicle_details.color}</p>
                    </div>
                    <div>
                        <p><strong>Vehicle Status:</strong> {report_data.client_vehicle_status}</p>
                        <p><strong>Uploaded By:</strong> {report_data.upload_details.uploaded_by}</p>
                        <p><strong>Upload Date:</strong> {report_data.upload_details.uploaded_on}</p>
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>Damage Assessment</h2>
                <div class="damage-details">
                    <p><strong>Damage Side:</strong> {report_data.detected_damages.damage_side}</p>
                    <p><strong>Area of Damage:</strong> {report_data.detected_damages.area_of_damage}</p>
                    <p><strong>Type of Damage:</strong> {report_data.detected_damages.type_of_damage}</p>
                    <p><strong>Severity:</strong> {report_data.detected_damages.severity}</p>
                    <p><strong>Confidence Level:</strong> {report_data.detected_damages.confidence_percent}%</p>
                    <p><strong>Total Damaged Points:</strong> {report_data.detected_damages.total_damaged_points_identified}</p>
                    {f'<p><strong>Unrelated Damage:</strong> {report_data.client_unrelated_damage}</p>' if report_data.client_unrelated_damage else ''}
                </div>
            </div>

            <div class="section">
                <h2>AI Analysis & Recommendations</h2>
                <div class="ai-analysis">
                    <p><strong>Suggested Actions:</strong> {report_data.detected_damages.ai_suggested_actions}</p>
                    <p><strong>Estimated Work Category:</strong> {report_data.summary.estimated_work_category}</p>
                </div>
            </div>

            <div class="section">
                <h2>Summary</h2>
                <p><strong>Total Damage Points:</strong> {report_data.summary.total_by_severity}</p>
                <p><strong>Primary Damage Area:</strong> {report_data.summary.area}</p>
                <p><strong>Work Category:</strong> {report_data.summary.estimated_work_category}</p>
            </div>

            <div class="section">
                <h2>Confirmation</h2>
                <p><strong>Confirmed By:</strong> {report_data.confirmation.confirmed_by}</p>
                <p><strong>Confirmed At:</strong> {report_data.confirmation.confirmed_at}</p>
            </div>
        </body>
        </html>
        """
        
        # Generate PDF using weasyprint
        pdf_io = io.BytesIO()
        HTML(string=html_content).write_pdf(pdf_io)
        return pdf_io.getvalue()

    def _compose_report_for_client_vehicle(self, claim_id: int, client_vehicle_id: int) -> ComprehensiveVehicleDamageReport:
        from sqlalchemy.orm import joinedload

        claim = self.db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")

        v = (
            self.db.query(VehicleDetail)
            .options(
                joinedload(VehicleDetail.vehicle_status),
                joinedload(VehicleDetail.ai_reports).joinedload(VehicleDamageAIReport.images),
            )
            .filter(VehicleDetail.id == client_vehicle_id, VehicleDetail.claim_id == claim_id)
            .first()
        )
        if not v:
            raise ValueError(f"Client vehicle {client_vehicle_id} not found for claim {claim_id}")

        latest_ai_report = None
        if v.ai_reports:
            latest_ai_report = max(v.ai_reports, key=lambda x: x.created_at)

        uploaded_by = "System"
        if latest_ai_report and latest_ai_report.created_by:
            user = self.db.query(User).filter(User.id == latest_ai_report.created_by).first()
            if user:
                uploaded_by = f"{user.first_name} {user.last_name}".strip() or user.email

        from datetime import datetime

        report_details = {
            "claim_id": f"A{claim_id:09d}",
            "report_id": f"A{claim_id:011d}",
            "generated_on": latest_ai_report.created_at.strftime("%d/%m/%Y, %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
        }
        upload_details = {
            "uploaded_by": uploaded_by,
            "file_name": "Damage Report",
            "uploaded_on": latest_ai_report.created_at.strftime("%d/%m/%Y, %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
            "source": "Camera",
        }
        vehicle_details = {
            "vehicle_reg_no": v.registration,
            "make_model": f"{v.make} {v.model}",
            "color": v.color or "Unknown",
            "year": "2022",
        }
        if latest_ai_report:
            detected_damages = {
                "damage_side": latest_ai_report.damage_side or "",
                "area_of_damage": latest_ai_report.area_of_damage or "",
                "type_of_damage": latest_ai_report.type_of_damage or "",
                "severity": latest_ai_report.severity or "",
                "confidence_percent": latest_ai_report.confidence_percent or 0,
                "total_damaged_points_identified": latest_ai_report.total_damaged_points_identified or 0,
                "ai_suggested_actions": latest_ai_report.suggested_repair_action or "",
            }
        else:
            detected_damages = {
                "damage_side": "",
                "area_of_damage": v.damage_area or "",
                "type_of_damage": "",
                "severity": "",
                "confidence_percent": 0,
                "total_damaged_points_identified": 0,
                "ai_suggested_actions": "Manual assessment required",
            }

        uploaded_images = []
        if latest_ai_report and latest_ai_report.images:
            for img in latest_ai_report.images:
                uploaded_images.append({
                    "file_path": get_full_url(img.file_path),
                    "original_filename": img.original_filename or "damage_image.jpg",
                    "thumbnail_url": get_full_url(img.file_path),
                })

        confirmation = {
            "confirmed_by": uploaded_by,
            "confirmed_at": latest_ai_report.created_at.strftime("%d/%m/%Y on %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y on %I:%M %p"),
        }
        summary = {
            "total_by_severity": (latest_ai_report.total_damaged_points_identified if latest_ai_report else 0) or 0,
            "area": (latest_ai_report.area_of_damage if latest_ai_report else v.damage_area) or "",
            "estimated_work_category": (latest_ai_report.suggested_repair_action if latest_ai_report else "Manual assessment required") or "Manual assessment required",
        }

        data = {
            "report_details": report_details,
            "upload_details": upload_details,
            "vehicle_details": vehicle_details,
            "client_unrelated_damage": v.unrelated_damage or "",
            "client_vehicle_status": v.vehicle_status.label if getattr(v, "vehicle_status", None) else "",
            "detected_damages": detected_damages,
            "uploaded_images": uploaded_images,
            "confirmation": confirmation,
            "summary": summary,
        }
        return ComprehensiveVehicleDamageReport(**data)

    def _compose_report_for_third_party(self, claim_id: int, third_party_vehicle_id: int) -> ComprehensiveVehicleDamageReport:
        from sqlalchemy.orm import joinedload
        from datetime import datetime

        tp = (
            self.db.query(ThirdPartyVehicle)
            .options(
                joinedload(ThirdPartyVehicle.ai_reports).joinedload(VehicleDamageAIReport.images),
            )
            .filter(ThirdPartyVehicle.id == third_party_vehicle_id)
            .first()
        )
        if not tp:
            raise ValueError(f"Third-party vehicle {third_party_vehicle_id} not found")

        latest_ai_report = None
        if getattr(tp, "ai_reports", None):
            latest_ai_report = max(tp.ai_reports, key=lambda x: x.created_at)

        uploaded_by = "System"
        if latest_ai_report and latest_ai_report.created_by:
            user = self.db.query(User).filter(User.id == latest_ai_report.created_by).first()
            if user:
                uploaded_by = f"{user.first_name} {user.last_name}".strip() or user.email

        report_details = {
            "claim_id": f"A{claim_id:09d}",
            "report_id": f"TP{third_party_vehicle_id:011d}",
            "generated_on": latest_ai_report.created_at.strftime("%d/%m/%Y, %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
        }
        upload_details = {
            "uploaded_by": uploaded_by,
            "file_name": "Third-Party Damage Report",
            "uploaded_on": latest_ai_report.created_at.strftime("%d/%m/%Y, %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
            "source": "Camera",
        }
        vehicle_details = {
            "vehicle_reg_no": tp.registration,
            "make_model": f"{tp.make} {tp.model}",
            "color": tp.color or "Unknown",
            "year": "2022",
        }
        if latest_ai_report:
            detected_damages = {
                "damage_side": latest_ai_report.damage_side or "",
                "area_of_damage": latest_ai_report.area_of_damage or "",
                "type_of_damage": latest_ai_report.type_of_damage or "",
                "severity": latest_ai_report.severity or "",
                "confidence_percent": latest_ai_report.confidence_percent or 0,
                "total_damaged_points_identified": latest_ai_report.total_damaged_points_identified or 0,
                "ai_suggested_actions": latest_ai_report.suggested_repair_action or "",
            }
        else:
            detected_damages = {
                "damage_side": "",
                "area_of_damage": tp.damage_area or "",
                "type_of_damage": "",
                "severity": "",
                "confidence_percent": 0,
                "total_damaged_points_identified": 0,
                "ai_suggested_actions": "Manual assessment required",
            }

        uploaded_images = []
        if latest_ai_report and latest_ai_report.images:
            for img in latest_ai_report.images:
                uploaded_images.append({
                    "file_path": get_full_url(img.file_path),
                    "original_filename": img.original_filename or "damage_image.jpg",
                    "thumbnail_url": get_full_url(img.file_path),
                })

        confirmation = {
            "confirmed_by": uploaded_by,
            "confirmed_at": latest_ai_report.created_at.strftime("%d/%m/%Y on %I:%M %p") if latest_ai_report else datetime.now().strftime("%d/%m/%Y on %I:%M %p"),
        }
        summary = {
            "total_by_severity": (latest_ai_report.total_damaged_points_identified if latest_ai_report else 0) or 0,
            "area": (latest_ai_report.area_of_damage if latest_ai_report else tp.damage_area) or "",
            "estimated_work_category": (latest_ai_report.suggested_repair_action if latest_ai_report else "Manual assessment required") or "Manual assessment required",
        }

        data = {
            "report_details": report_details,
            "upload_details": upload_details,
            "vehicle_details": vehicle_details,
            "client_unrelated_damage": tp.unrelated_damage or "",
            "client_vehicle_status": "",  # not tracked for third-party in UI summary
            "detected_damages": detected_damages,
            "uploaded_images": uploaded_images,
            "confirmation": confirmation,
            "summary": summary,
        }
        return ComprehensiveVehicleDamageReport(**data)

    def send_damage_report_email(self, claim_id: int, recipient_email: str, recipient_name: str = "Recipient", client_vehicle_id: int | None = None, third_party_vehicle_id: int | None = None) -> str:
        """Send damage report email with one or both PDFs depending on IDs provided"""
        try:
            attachments: list[Attachment] = []

            built_reports: list[tuple[str, ComprehensiveVehicleDamageReport]] = []

            if client_vehicle_id:
                cv_report = self._compose_report_for_client_vehicle(claim_id, client_vehicle_id)
                built_reports.append((f"damage_report_client_{client_vehicle_id}.pdf", cv_report))

            if third_party_vehicle_id:
                tp_report = self._compose_report_for_third_party(claim_id, third_party_vehicle_id)
                built_reports.append((f"damage_report_thirdparty_{third_party_vehicle_id}.pdf", tp_report))

            # Fallback: if no IDs provided, send the comprehensive report for claim
            if not built_reports:
                report_data_dict = get_comprehensive_vehicle_damage_report(claim_id, self.db)
                report_data = ComprehensiveVehicleDamageReport(**report_data_dict)
                built_reports.append((f"damage_report_{report_data.report_details.report_id}.pdf", report_data))

            # Build email HTML content based on first report
            html_content = self._build_email_html(built_reports[0][1], recipient_name)
            
            # Build one or more PDF attachments.
            email_attachments = []
            for filename, rpt in built_reports:
                pdf_content = self._generate_pdf_report(rpt)
                email_attachments.append({
                    "name": filename,
                    "content_bytes": base64.b64encode(pdf_content).decode(),
                    "content_type": "application/pdf",
                })

            # Graph-first so it reaches Outlook (logo auto-attached via
            # cid:companylogo); SendGrid fallback.
            from appflow.services.email_delivery import send_email as deliver_email
            deliver_email(
                to=recipient_email,
                subject=f"Vehicle Damage Report - Claim A{claim_id:09d}",
                html=html_content,
                attachments=email_attachments,
            )

            filenames = ", ".join([name for name, _ in built_reports])
            return f"Damage report email sent successfully to {recipient_email}. Attachments: {filenames}"
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error sending damage report email: {str(e)}")

    def _generate_damage_report_pdf(
        self, 
        claim_id: int, 
        client_vehicle: VehicleDetail, 
        recipient_name: str, 
        custom_message: Optional[str] = None
    ) -> bytes:
        """
        Generate PDF report for vehicle damage using weasyprint
        """
        from datetime import datetime
        
        # Get latest AI report for client vehicle
        latest_client_ai_report = None
        if client_vehicle.ai_reports:
            latest_client_ai_report = max(client_vehicle.ai_reports, key=lambda x: x.created_at)

        # Get third-party vehicles with AI reports
        third_party_vehicles = []
        for tp_vehicle in client_vehicle.third_party_vehicles:
            latest_tp_ai_report = None
            if tp_vehicle.ai_reports:
                latest_tp_ai_report = max(tp_vehicle.ai_reports, key=lambda x: x.created_at)
            third_party_vehicles.append({
                'vehicle': tp_vehicle,
                'ai_report': latest_tp_ai_report
            })

        # Build PDF HTML content (similar to email but optimized for PDF)
        pdf_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Vehicle Damage AI Report - Claim {claim_id}</title>
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{ 
                    font-family: Arial, sans-serif; 
                    margin: 0; 
                    padding: 0;
                    color: #333;
                }}
                .header {{ 
                    text-align: center; 
                    border-bottom: 3px solid #000000; 
                    padding-bottom: 20px; 
                    margin-bottom: 30px; 
                }}
                .header h1 {{
                    color: #000000;
                    margin: 10px 0;
                }}
                .section {{ 
                    margin-bottom: 25px; 
                    page-break-inside: avoid;
                }}
                .section-title {{ 
                    color: #000000; 
                    font-size: 16px; 
                    font-weight: bold; 
                    margin-bottom: 12px; 
                    border-bottom: 2px solid #000000; 
                    padding-bottom: 5px; 
                }}
                .vehicle-info {{ 
                    background-color: #f8f9fa; 
                    padding: 15px; 
                    border-radius: 5px; 
                    margin-bottom: 15px; 
                }}
                .vehicle-info p {{
                    margin: 8px 0;
                }}
                .damage-table {{ 
                    width: 100%; 
                    border-collapse: collapse; 
                    margin-top: 12px; 
                }}
                .damage-table th, .damage-table td {{ 
                    border: 1px solid #ddd; 
                    padding: 10px; 
                    text-align: left; 
                }}
                .damage-table th {{ 
                    background-color: #000000; 
                    color: white; 
                    font-weight: bold;
                }}
                .damage-table tr:nth-child(even) {{ 
                    background-color: #f2f2f2; 
                }}
                .severity-high {{ 
                    color: #dc3545; 
                    font-weight: bold; 
                }}
                .severity-medium {{ 
                    color: #ffc107; 
                    font-weight: bold; 
                }}
                .severity-low {{ 
                    color: #28a745; 
                    font-weight: bold; 
                }}
                .footer {{ 
                    text-align: center; 
                    margin-top: 30px; 
                    padding-top: 15px; 
                    border-top: 1px solid #ddd; 
                    color: #666; 
                    font-size: 12px;
                }}
                .confidence-badge {{
                    display: inline-block;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                .confidence-high {{
                    background-color: #d4edda;
                    color: #155724;
                }}
                .confidence-medium {{
                    background-color: #fff3cd;
                    color: #856404;
                }}
                .confidence-low {{
                    background-color: #f8d7da;
                    color: #721c24;
                }}
            </style>
        </head>
        <body>
                <div class="header">
                    <h1>Vehicle Damage AI Report</h1>
                <p><strong>Claim ID:</strong> {claim_id}</p>
                <p><strong>Generated on:</strong> {datetime.now().strftime('%d/%m/%Y at %I:%M %p')}</p>
                </div>

                <div class="section">
                    <h2 class="section-title">Report Summary</h2>
                    <p>Dear {recipient_name},</p>
                <p>This comprehensive AI-powered damage analysis report has been generated for your vehicle claim.</p>
                {f'<p><strong>Additional Notes:</strong> {custom_message}</p>' if custom_message else ''}
                </div>

                <div class="section">
                    <h2 class="section-title">Client Vehicle Details</h2>
                    <div class="vehicle-info">
                        <p><strong>Registration:</strong> {client_vehicle.registration}</p>
                        <p><strong>Make/Model:</strong> {client_vehicle.make} {client_vehicle.model}</p>
                    <p><strong>Body Type:</strong> {client_vehicle.body_type}</p>
                        <p><strong>Color:</strong> {client_vehicle.color or 'N/A'}</p>
                    </div>
                </div>
        """

        # Add client vehicle AI analysis if available
        if latest_client_ai_report:
            confidence_class = "confidence-high" if (latest_client_ai_report.confidence_percent or 0) >= 80 else "confidence-medium" if (latest_client_ai_report.confidence_percent or 0) >= 60 else "confidence-low"
            severity_class = f"severity-{(latest_client_ai_report.severity or 'low').lower()}"
            
            pdf_html += f"""
                <div class="section">
                    <h2 class="section-title">Client Vehicle AI Damage Analysis</h2>
                    <table class="damage-table">
                        <tr>
                            <th>Field</th>
                            <th>Value</th>
                        </tr>
                        <tr>
                            <td><strong>Damage Side</strong></td>
                            <td>{latest_client_ai_report.damage_side or 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Area of Damage</strong></td>
                            <td>{latest_client_ai_report.area_of_damage or 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Type of Damage</strong></td>
                            <td>{latest_client_ai_report.type_of_damage or 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Severity</strong></td>
                            <td><span class="{severity_class}">{latest_client_ai_report.severity or 'N/A'}</span></td>
                        </tr>
                        <tr>
                            <td><strong>Confidence</strong></td>
                            <td><span class="confidence-badge {confidence_class}">{latest_client_ai_report.confidence_percent or 0}%</span></td>
                        </tr>
                        <tr>
                            <td><strong>Total Damaged Points</strong></td>
                            <td>{latest_client_ai_report.total_damaged_points_identified or 0}</td>
                        </tr>
                        <tr>
                            <td><strong>Suggested Repair Action</strong></td>
                            <td>{latest_client_ai_report.suggested_repair_action or 'N/A'}</td>
                        </tr>
                    </table>
                </div>
            """

        # Add third-party vehicles if any
        for idx, tp_data in enumerate(third_party_vehicles, 1):
            tp_vehicle = tp_data['vehicle']
            tp_ai_report = tp_data['ai_report']

            pdf_html += f"""
                <div class=\"section\">\n                    <h2 class=\"section-title\">Third-Party Vehicle {idx} Details</h2>\n                    <div class=\"vehicle-info\">\n                        <p><strong>Registration:</strong> {tp_vehicle.registration}</p>\n                        <p><strong>Make/Model:</strong> {tp_vehicle.make} {tp_vehicle.model}</p>\n                        <p><strong>Color:</strong> {tp_vehicle.color or 'N/A'}</p>\n                    </div>\n                </div>\n                """

            if tp_ai_report:
                tp_confidence_class = "confidence-high" if (tp_ai_report.confidence_percent or 0) >= 80 else "confidence-medium" if (tp_ai_report.confidence_percent or 0) >= 60 else "confidence-low"
                tp_severity_class = f"severity-{(tp_ai_report.severity or 'low').lower()}"

                pdf_html += f"""
                    <div class=\"section\">\n                        <h2 class=\"section-title\">Third-Party Vehicle {idx} AI Damage Analysis</h2>\n                        <table class=\"damage-table\">\n                            <tr>\n                                <th>Field</th>\n                                <th>Value</th>\n                            </tr>\n                            <tr>\n                                <td><strong>Damage Side</strong></td>\n                                <td>{tp_ai_report.damage_side or 'N/A'}</td>\n                            </tr>\n                            <tr>\n                                <td><strong>Area of Damage</strong></td>\n                                <td>{tp_ai_report.area_of_damage or 'N/A'}</td>\n                            </tr>\n                            <tr>\n                                <td><strong>Type of Damage</strong></td>\n                                <td>{tp_ai_report.type_of_damage or 'N/A'}</td>\n                            </tr>\n                            <tr>\n                                <td><strong>Severity</strong></td>\n                                <td><span class=\"{tp_severity_class}\">{tp_ai_report.severity or 'N/A'}</span></td>\n                            </tr>\n                            <tr>\n                                <td><strong>Confidence</strong></td>\n                                <td><span class=\"confidence-badge {tp_confidence_class}\">{tp_ai_report.confidence_percent or 0}%</span></td>\n                            </tr>\n                            <tr>\n                                <td><strong>Total Damaged Points</strong></td>\n                                <td>{tp_ai_report.total_damaged_points_identified or 0}</td>\n                            </tr>\n                            <tr>\n                                <td><strong>Suggested Repair Action</strong></td>\n                                <td>{tp_ai_report.suggested_repair_action or 'N/A'}</td>\n                            </tr>\n                        </table>\n                    </div>\n                """

        pdf_html += """
            <div class="footer">
                <p>This report was generated automatically by AI analysis. For any questions, please contact our support team.</p>
                <p>&copy; 2025 ProClaim - All Rights Reserved</p>
            </div>
        </body>
        </html>
        """

        # Generate PDF using weasyprint
        pdf_file = HTML(string=pdf_html).write_pdf()
        return pdf_file

    def send_comprehensive_damage_report_email(
        self, 
        claim_id: int, 
        recipient_email: str, 
        recipient_name: str = "Recipient",
        custom_message: Optional[str] = None
    ) -> str:
        """
        Send comprehensive damage report email with all vehicle data, AI analysis, and PDF attachment
        """
        try:
            # Fetch client vehicle data
            client_vehicle = (
                self.db.query(VehicleDetail)
                .options(
                    joinedload(VehicleDetail.ai_reports).joinedload(VehicleDamageAIReport.images),
                    joinedload(VehicleDetail.third_party_vehicles).joinedload(ThirdPartyVehicle.ai_reports).joinedload(VehicleDamageAIReport.images)
                )
                .filter(VehicleDetail.claim_id == claim_id)
                .first()
            )
            
            if not client_vehicle:
                raise ValueError(f"No client vehicle found for claim {claim_id}")

            # Build comprehensive HTML email with all vehicle data
            html_content = self._build_comprehensive_email_html(
                client_vehicle, 
                recipient_name, 
                custom_message
            )

            # Generate PDF report
            pdf_content = self._generate_damage_report_pdf(
                claim_id,
                client_vehicle,
                recipient_name,
                custom_message
            )

            # Create email message
            email_attachments = []

            # PDF report.
            email_attachments.append({
                "name": f"Vehicle_Damage_Report_Claim_{claim_id}.pdf",
                "content_bytes": base64.b64encode(pdf_content).decode(),
                "content_type": "application/pdf",
            })

            # Collect all vehicle damage image attachments (reuse the existing
            # SendGrid Attachment builder, then read its bytes back out).
            image_counter = 1

            def _collect_images(reports):
                nonlocal image_counter
                for ai_report in (reports or []):
                    for image in (ai_report.images or []):
                        att = self._download_and_prepare_image_attachment(
                            image.file_path, image.original_filename, image_counter
                        )
                        if att:
                            email_attachments.append({
                                "name": att.file_name.file_name,
                                "content_bytes": att.file_content.file_content,
                                "content_type": att.file_type.file_type,
                            })
                            image_counter += 1

            _collect_images(client_vehicle.ai_reports)
            if client_vehicle.third_party_vehicles:
                for tp_vehicle in client_vehicle.third_party_vehicles:
                    _collect_images(tp_vehicle.ai_reports)

            # Graph-first so it reaches Outlook (logo auto-attached via
            # cid:companylogo); SendGrid fallback.
            from appflow.services.email_delivery import send_email as deliver_email
            deliver_email(
                to=recipient_email,
                subject=f"Vehicle Damage AI Report - Claim {claim_id}",
                html=html_content,
                attachments=email_attachments,
            )

            # Build success message with image count
            total_images = image_counter - 1
            success_message = f"Comprehensive damage report email with PDF attachment sent successfully to {recipient_email}"
            if total_images > 0:
                success_message += f" (includes {total_images} vehicle damage image(s))"
            
            return success_message
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error sending comprehensive damage report email: {str(e)}")

    def _build_comprehensive_email_html(
        self, 
        client_vehicle: VehicleDetail, 
        recipient_name: str, 
        custom_message: Optional[str] = None
    ) -> str:
        """
        Build comprehensive HTML email content with all vehicle data and AI analysis
        """
        from datetime import datetime
        
        # Get latest AI report for client vehicle
        latest_client_ai_report = None
        if client_vehicle.ai_reports:
            latest_client_ai_report = max(client_vehicle.ai_reports, key=lambda x: x.created_at)

        # Get third-party vehicles with AI reports
        third_party_vehicles = []
        for tp_vehicle in client_vehicle.third_party_vehicles:
            latest_tp_ai_report = None
            if tp_vehicle.ai_reports:
                latest_tp_ai_report = max(tp_vehicle.ai_reports, key=lambda x: x.created_at)
            third_party_vehicles.append({
                'vehicle': tp_vehicle,
                'ai_report': latest_tp_ai_report
            })

        # Build HTML content
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Vehicle Damage AI Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; border-bottom: 2px solid #000000; padding-bottom: 20px; margin-bottom: 30px; }}
                .logo {{ max-width: 150px; height: auto; }}
                .section {{ margin-bottom: 30px; }}
                .section-title {{ color: #000000; font-size: 18px; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
                .vehicle-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .damage-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                .damage-table th, .damage-table td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                .damage-table th {{ background-color: #000000; color: white; }}
                .damage-table tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .images-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }}
                .image-item {{ text-align: center; }}
                .image-item img {{ max-width: 100%; height: 150px; object-fit: cover; border-radius: 5px; border: 1px solid #ddd; }}
                .image-caption {{ font-size: 12px; color: #666; margin-top: 5px; }}
                .severity-high {{ color: #dc3545; font-weight: bold; }}
                .severity-medium {{ color: #ffc107; font-weight: bold; }}
                .severity-low {{ color: #28a745; font-weight: bold; }}
                .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="cid:companylogo" alt="Company Logo" class="logo">
                    <h1>Vehicle Damage AI Report</h1>
                    <p>Generated on {datetime.now().strftime('%d/%m/%Y at %I:%M %p')}</p>
                </div>

                <div class="section">
                    <h2 class="section-title">Report Summary</h2>
                    <p>Dear {recipient_name},</p>
                    <p>Please find below the comprehensive AI-powered damage analysis for your vehicle claim.</p>
                    {f'<p><strong>Additional Message:</strong> {custom_message}</p>' if custom_message else ''}
            </div>
        """

        # Add client vehicle AI analysis if available
        # if latest_client_ai_report:
        #     html += f"""
        #         <div class="section">
        #             <h2 class="section-title">Client Vehicle AI Damage Analysis</h2>
        #             <table class="damage-table">
        #                 <tr>
        #                     <th>Field</th>
        #                     <th>Value</th>
        #                 </tr>
        #                 <tr>
        #                     <td><strong>Damage Side</strong></td>
        #                     <td>{latest_client_ai_report.damage_side or 'N/A'}</td>
        #                 </tr>
        #                 <tr>
        #                     <td><strong>Area of Damage</strong></td>
        #                     <td>{latest_client_ai_report.area_of_damage or 'N/A'}</td>
        #                 </tr>
        #                 <tr>
        #                     <td><strong>Type of Damage</strong></td>
        #                     <td>{latest_client_ai_report.type_of_damage or 'N/A'}</td>
        #                 </tr>
        #                 <tr>
        #                     <td><strong>Severity</strong></td>
        #                     <td class="severity-{latest_client_ai_report.severity.lower() if latest_client_ai_report.severity else 'low'}">{latest_client_ai_report.severity or 'N/A'}</td>
        #                 </tr>
        #                 <tr>
        #                     <td><strong>Confidence</strong></td>
        #                     <td>{latest_client_ai_report.confidence_percent or 0}%</td>
        #                 </tr>
        #                 <tr>
        #                     <td><strong>Total Damage Points</strong></td>
        #                     <td>{latest_client_ai_report.total_damaged_points_identified or 0}</td>
        #                 </tr>
        #                 <tr>
        #                     <td><strong>AI Suggested Actions</strong></td>
        #                     <td>{latest_client_ai_report.suggested_repair_action or 'N/A'}</td>
        #                 </tr>
        #             </table>
        #         </div>
        #     """

        #     # Add client vehicle images
        #     if latest_client_ai_report.images:
        #         html += """
        #         <div class="section">
        #             <h2 class="section-title">Client Vehicle Damage Images</h2>
        #             <div class="images-grid">
        #         """
        #         for img in latest_client_ai_report.images:
        #             html += f"""
        #                 <div class="image-item">
        #                     <img src="{get_full_url(img.file_path)}" alt="Damage Image">
        #                     <div class="image-caption">{img.original_filename}</div>
        #                 </div>
        #             """
        #         html += """
        #             </div>
        #         </div>
        #         """

        # # Add third-party vehicles if available
        # if third_party_vehicles:
        #     html += """
        #         <div class="section">
        #             <h2 class="section-title">Third-Party Vehicle Analysis</h2>
        #     """
            
        #     for tp_data in third_party_vehicles:
        #         tp_vehicle = tp_data['vehicle']
        #         tp_ai_report = tp_data['ai_report']
                
        #         html += f"""
        #             <div class="vehicle-info">
        #                 <h3>Third-Party Vehicle {tp_vehicle.sequence or 1}</h3>
        #                 <p><strong>Registration:</strong> {tp_vehicle.registration}</p>
        #                 <p><strong>Make/Model:</strong> {tp_vehicle.make} {tp_vehicle.model}</p>
        #                 <p><strong>Color:</strong> {tp_vehicle.color or 'N/A'}</p>
        #         """
                
        #         if tp_ai_report:
        #             html += f"""
        #                 <table class="damage-table">
        #                     <tr>
        #                         <th>Field</th>
        #                         <th>Value</th>
        #                     </tr>
        #                     <tr>
        #                         <td><strong>Damage Side</strong></td>
        #                         <td>{tp_ai_report.damage_side or 'N/A'}</td>
        #                     </tr>
        #                     <tr>
        #                         <td><strong>Area of Damage</strong></td>
        #                         <td>{tp_ai_report.area_of_damage or 'N/A'}</td>
        #                     </tr>
        #                     <tr>
        #                         <td><strong>Type of Damage</strong></td>
        #                         <td>{tp_ai_report.type_of_damage or 'N/A'}</td>
        #                     </tr>
        #                     <tr>
        #                         <td><strong>Severity</strong></td>
        #                         <td class="severity-{tp_ai_report.severity.lower() if tp_ai_report.severity else 'low'}">{tp_ai_report.severity or 'N/A'}</td>
        #                     </tr>
        #                     <tr>
        #                         <td><strong>Confidence</strong></td>
        #                         <td>{tp_ai_report.confidence_percent or 0}%</td>
        #                     </tr>
        #                     <tr>
        #                         <td><strong>Total Damage Points</strong></td>
        #                         <td>{tp_ai_report.total_damaged_points_identified or 0}</td>
        #                     </tr>
        #                     <tr>
        #                         <td><strong>AI Suggested Actions</strong></td>
        #                         <td>{tp_ai_report.suggested_repair_action or 'N/A'}</td>
        #                     </tr>
        #                 </table>
        #             """
                    
        #             # Add third-party vehicle images
        #             if tp_ai_report.images:
        #                 html += """
        #                 <div class="images-grid">
        #                 """
        #                 for img in tp_ai_report.images:
        #                     html += f"""
        #                         <div class="image-item">
        #                             <img src="{get_full_url(img.file_path)}" alt="Third-Party Damage Image">
        #                             <div class="image-caption">{img.original_filename}</div>
        #                         </div>
        #                     """
        #                 html += """
        #                 </div>
        #                 """
                
        #         html += "</div>"
            
        #     html += "</div>"

        # # Add footer
        # html += """
        #         <div class="footer">
        #             <p>This report was generated automatically using AI-powered damage detection technology.</p>
        #             <p>For any questions or concerns, please contact our support team.</p>
        #             <p><strong>ProClaim Team</strong></p>
        #         </div>
        #     </div>
        # </body>
        # </html>
        # """

        return html
