import os
import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Attachment, FileContent, FileName, FileType, Disposition, ContentId
)
from dotenv import load_dotenv

load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL = os.getenv("SENDGRID_SENDER", "no-replynationwideassist@outlook.com")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5174")

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "logo.png")
with open(_LOGO_PATH, "rb") as _f:
    _LOGO_ENCODED = base64.b64encode(_f.read()).decode()

def _logo_attachment() -> Attachment:
    return Attachment(
        FileContent(_LOGO_ENCODED),
        FileName("logo.png"),
        FileType("image/png"),
        Disposition("inline"),
        ContentId("companylogo"),
    )


def build_invite_email_html(invite_link: str) -> str:
    font = "'Stack Sans Headline', Helvetica, Arial, sans-serif"
    return f"""
    <div style="font-family: {font}; background-color: #ffffff;">
      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: {font}; background-color: #ffffff;">
        <tr>
          <td style="padding: 40px 0;">
            <table align="center" border="0" cellpadding="0" cellspacing="0" width="600"
              style="background-color: #ffffff; border-collapse: collapse;">
              <tr>
                <td align="center" style="padding: 48px;">
                  <img src="cid:companylogo" alt="Nationwide Assist" width="48" height="46" style="display: block; margin: 0 auto 24px auto; border: 0;" />

                  <h2 style="color: #000000; font-size: 20px; font-weight: 600; font-family: {font}; margin: 0 0 16px 0; line-height: 1.0;">Hi</h2>

                  <p style="color: #444444; font-size: 14px; font-weight: 400; font-family: {font}; line-height: 1.57; margin: 0 0 24px 0;">
                    You have been added as a user to the <br />
                    <span style="font-weight: 600;">Nationwide Assist CRM</span>
                  </p>

                  <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td align="center" style="padding-bottom: 32px;">
                        <p style="color: #444444; font-size: 12px; font-weight: 400; font-family: {font}; margin: 0 0 12px 0; max-width: 424px;">
                          To activate your account and set your password, please click the link below:
                        </p>

                        <a href="{invite_link}" style="color: #0352FD; font-size: 12px; font-family: {font}; text-decoration: none; word-break: break-all;">
                          {invite_link}
                        </a>
                      </td>
                    </tr>
                  </table>

                  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 394px;">
                    <tr>
                      <td align="center" style="padding-bottom: 48px;">
                        <p style="color: #444444; font-size: 12px; line-height: 1.6; font-weight: 600; font-family: {font}; margin: 0 0 24px 0;">
                          For security reasons, this link will expire in 24 hours.<br />
                          If the link expires, please contact your admin to request a new activation email.
                        </p>

                        <p style="color: #444444; font-size: 12px; font-weight: 600; font-family: {font}; margin: 0;">
                          If you did not expect this invitation, you can safely ignore this message.
                        </p>
                      </td>
                    </tr>
                  </table>

                  <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td style="height: 1px; background-color: #CCCCCC; line-height: 1px; font-size: 1px;">&nbsp;</td>
                    </tr>
                  </table>

                  <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td align="center" style="padding-top: 32px; padding-bottom: 48px;">
                        <span style="color: #000000; font-size: 12px; font-weight: 400; font-family: {font};">Kind regards,</span><br />
                        <span style="color: #000000; font-size: 14px; font-weight: 600; font-family: {font};">Nationwide Assist IT / Systems Team</span>
                      </td>
                    </tr>
                  </table>

                  <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td align="center" style="padding: 16px;">
                        <span style="color: #888888; font-size: 12px; font-weight: 600; font-family: {font};">Security notice:</span>
                        <p style="color: #888888; font-size: 12px; font-weight: 400; font-family: {font}; margin: 4px 0 0 0; line-height: 1.4;">
                          Never share your login details with anyone. Nationwide Assist will never ask for your password by email.
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </div>
    """


def send_invite_email(recipient_email: str) -> None:
    invite_link = f"{FRONTEND_BASE_URL}/auth/reset-password?email={recipient_email}"

    # Graph-first so it reaches Outlook (logo auto-attached via cid:companylogo);
    # SendGrid fallback.
    from appflow.services.email_delivery import send_email as deliver_email
    deliver_email(
        to=recipient_email,
        subject="Password Reset - Secure Invitation Link",
        html=build_invite_email_html(invite_link),
    )



def build_otp_email_html(otp: str, first_name: str = "") -> str:
    greeting = f"Hi, {first_name}" if first_name else "Hi"
    font = "'Stack Sans Headline', Helvetica, Arial, sans-serif"
    return f"""
    <div style="font-family: {font}; background-color: #ffffff;">
      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: {font}; background-color: #ffffff;">
        <tr>
          <td align="center" style="padding: 40px 0;">
            <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; padding: 48px;">

              <tr>
                <td align="center" style="padding-bottom: 24px;">
                  <img src="cid:companylogo" alt="Nationwide Assist" width="48" height="46" style="display: block; border: 0;" />
                </td>
              </tr>

              <tr>
                <td align="center" style="padding-bottom: 16px;">
                  <h2 style="margin: 0; color: #000000; font-size: 20px; font-weight: 600; font-family: {font}; line-height: 1.0;">
                    {greeting}
                  </h2>
                </td>
              </tr>

              <tr>
                <td align="center" style="padding-bottom: 34px;">
                  <p style="margin: 0; color: #444444; font-size: 14px; font-weight: 400; font-family: {font}; line-height: 1.57;">
                    Your One-Time Password (OTP) for accessing<br>
                    your Nationwide Assist CRM account is
                  </p>
                </td>
              </tr>

              <tr>
                <td align="center" style="padding-bottom: 56px;">
                  <div style="color: #0352FD; font-size: 40px; font-weight: 600; font-family: {font}; letter-spacing: 14px; line-height: 1.0;">
                    {otp}
                  </div>
                </td>
              </tr>

              <tr>
                <td align="center" style="padding-bottom: 48px;">
                  <div style="max-width: 394px; margin: 0 auto; color: #444444; font-size: 12px; font-weight: 600; font-family: {font}; line-height: 1.6; text-align: center;">
                    <p style="margin: 0;">This OTP is valid for 5 minutes and can only be used once.</p>
                    <br>
                    <p style="margin: 0;">
                      If you did not request this OTP, you can safely ignore this email or contact your system administrator.
                    </p>
                  </div>
                </td>
              </tr>

              <tr>
                <td style="height: 1px; background-color: #CCCCCC; line-height: 1px; font-size: 1px; padding: 0;">&nbsp;</td>
              </tr>

              <tr>
                <td align="center" style="padding-top: 40px; padding-bottom: 32px;">
                  <span style="color: #000000; font-size: 12px; font-weight: 400; font-family: {font};">Kind regards,</span><br>
                  <span style="color: #000000; font-size: 14px; font-weight: 600; font-family: {font};">Nationwide Assist IT / Systems Team</span>
                </td>
              </tr>

              <tr>
                <td align="center" style="padding: 16px;">
                  <span style="color: #888888; font-size: 12px; font-weight: 600; font-family: {font};">Security notice:</span><br>
                  <p style="color: #888888; font-size: 12px; font-weight: 400; font-family: {font}; margin: 4px 0 0 0; line-height: 1.4; max-width: 398px; text-align: center;">
                    Never share your login details with anyone. Nationwide Assist will never ask for your password by email.
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </div>
    """


def send_otp_email(recipient_email: str, otp: str, first_name: str = "") -> None:
    # Graph-first so it reaches Outlook (logo auto-attached via cid:companylogo);
    # SendGrid fallback.
    from appflow.services.email_delivery import send_email as deliver_email
    deliver_email(
        to=recipient_email,
        subject="Your One-Time Password (OTP)",
        html=build_otp_email_html(otp, first_name),
    )
