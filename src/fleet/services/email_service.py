"""Fleet outbound email.

- ``send_hire_email``: free-form subject/message + attachments (branded box shell).
- ``send_deposit_refund_email``: a structured, boxed template matching the on/off-hire
  emails (logo, key/value boxes, "Kind regards, Nationwide Assist" footer).

The logo is EMBEDDED (cid:companylogo), sized 48x46 to match the OTP email. Embedded
because email clients (esp. Outlook) block remote/URL images by default, whereas an
inline cid image always renders. Reuses the host's Graph-first delivery via ``fleet.deps``.
"""
import base64
import os
from html import escape
from typing import List, Optional

from fleet.deps import send_email

# Fleet's own copy of the logo, embedded inline (cid) so it always renders.
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
try:
    with open(_LOGO_PATH, "rb") as _lf:
        _LOGO_B64 = base64.b64encode(_lf.read()).decode("ascii")
except Exception:  # pragma: no cover
    _LOGO_B64 = ""
_LOGO_IMG = '<img src="cid:companylogo" alt="Nationwide Assist" width="48" height="46" style="display:block;margin:0 auto 24px auto;border:0;" />'


def _logo_attachment() -> List[dict]:
    if not _LOGO_B64:
        return []
    return [{"name": "logo.png", "content_bytes": _LOGO_B64, "content_type": "image/png", "cid": "companylogo"}]


def build_attachment(filename: Optional[str], content_type: Optional[str], content: bytes) -> dict:
    return {
        "name": filename or "attachment",
        "content_bytes": base64.b64encode(content).decode("ascii"),
        "content_type": content_type or "application/octet-stream",
    }


# --------------------------------------------------------------------------- #
# Free-form email (branded box shell)
# --------------------------------------------------------------------------- #
_TEMPLATE = (
    '<div style="margin:0;padding:24px;background:#f3f4f6;font-family:Inter,Arial,sans-serif;">'
    '<div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;padding:24px;">'
    '<div style="text-align:center;">' + _LOGO_IMG + "</div>"
    '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:20px;white-space:pre-wrap;color:#111827;font-size:14px;line-height:1.6;">{{BODY}}</div>'
    '<div style="text-align:center;padding-top:16px;margin-top:16px;border-top:1px solid #eeeeee;font-size:12px;color:#6b7280;font-weight:bold;">ProClaim</div>'
    "</div></div>"
)


def send_hire_email(
    to: str,
    subject: str,
    body: str,
    attachments: Optional[List[dict]] = None,
    cc: Optional[str] = None,
) -> dict:
    html = _TEMPLATE.replace("{{BODY}}", escape(body or ""))
    # The logo is auto-embedded inline by GraphEmailService (cid:companylogo); do NOT
    # pass it as an attachment or it shows as a separate attachment tile.
    return send_email(to=to, subject=subject or "", html=html, attachments=list(attachments or []), cc=cc)


# --------------------------------------------------------------------------- #
# Structured deposit-refund template (boxed, matches on/off-hire emails)
# --------------------------------------------------------------------------- #
def _row(label: str, val: Optional[str]) -> str:
    return (
        '<div style="display:flex;justify-content:space-between;padding:5px 0;">'
        f'<span style="font-size:11px;color:#666;width:150px;">{escape(label)}</span>'
        f'<span style="font-size:11px;font-weight:700;text-align:left;flex:1;">{escape(val) if val else "N/A"}</span>'
        "</div>"
    )


def _divider() -> str:
    return '<div style="height:1px;background-color:#f1f1f1;margin:2px 0;"></div>'


def _box(inner: str) -> str:
    return f'<div style="max-width:460px;margin:0 auto 20px auto;border:1px solid #e2e8f0;border-radius:8px;padding:15px;">{inner}</div>'


def _heading(text: str) -> str:
    return f'<p style="font-weight:700;font-size:13px;margin:0 0 10px 0;">{escape(text)}</p>'


def render_deposit_refund(data: dict, include_logo: bool = True) -> str:
    g = lambda k: (data.get(k) or "")  # noqa: E731
    identity = _box(_divider().join([_row("Ref", g("ref")), _row("Hirer Name", g("hirer_name")), _row("Hirer Vehicle Registration", g("registration"))]))

    accounts_msg = (
        '<div style="max-width:460px;margin:0 auto 20px auto;text-align:center;font-size:13px;line-height:1.6;color:#334155;">'
        "<p>Please process a refund to the hirer's account in return of their security deposit minus any return charges, inclusive of VAT.</p>"
        "</div>"
    )

    deductions = _box(
        _heading("Refund Breakdown")
        + _divider().join([
            _row("Deposit Amount", g("deposit")),
            _row("Valeting Fee", g("valeting_fee")),
            _row("Vehicle Damages", g("vehicle_damages")),
            _row("Excess PPM Charges", g("excess_ppm")),
            _row("Hire Charges Unpaid", g("hire_charges_unpaid")),
            _row("Total Deductions", g("total_deductions")),
            _row("Refund Amount", g("refund_amount")),
        ])
    )

    bank = _box(
        _heading("Bank Details")
        + _divider().join([_row("Bank", g("bank")), _row("Account Name", g("account_name")), _row("Sort Code", g("sort_code")), _row("Account Number", g("account_number"))])
    )

    hire = _box(
        _heading("Hire Details")
        + _divider().join([_row("Hire Start Date", g("hire_start")), _row("Hire End Date", g("hire_end"))])
    )

    logo = ('<div style="text-align:center;">' + _LOGO_IMG + "</div>") if include_logo else ""
    return (
        '<div style="font-family:Arial,sans-serif;background:#ffffff;padding:20px;color:#334155;">'
        + logo
        + identity
        + accounts_msg
        + deductions
        + bank
        + hire
        + '<div style="text-align:center;font-size:12px;border-top:1px solid #eee;padding-top:20px;margin-top:10px;">'
        '<p style="font-weight:600;">Kind regards,<br>Nationwide Assist IT / Systems Team</p></div>'
        "</div>"
    )


def send_deposit_refund_email(to: str, subject: str, data: dict, cc: Optional[str] = None) -> dict:
    html = render_deposit_refund(data)
    # Logo auto-embeds inline via GraphEmailService (cid:companylogo) — not attached.
    return send_email(to=to, subject=subject or "Request Refund Deposit", html=html, cc=cc)


# --------------------------------------------------------------------------- #
# Structured Pay/Reimburse Hirer template (same boxed visual language)
# --------------------------------------------------------------------------- #
def render_pay_hirer(data: dict, include_logo: bool = True) -> str:
    g = lambda k: (data.get(k) or "")  # noqa: E731
    identity = _box(_divider().join([
        _row("Ref", g("ref")),
        _row("Hirer Name", g("hirer_name")),
        _row("Hire Vehicle Registration", g("registration")),
    ]))

    accounts_msg = (
        '<div style="max-width:460px;margin:0 auto 20px auto;text-align:center;font-size:13px;line-height:1.6;color:#334155;">'
        "<p>Please process a payment to this hirer as per the below.</p>"
        "</div>"
    )

    payment = _box(
        _heading("Payment Details")
        + _divider().join([
            _row("Amount To Pay", g("amount")),
            _row("Reason", g("reason")),
        ])
    )

    bank = _box(
        _heading("Bank Details")
        + _divider().join([
            _row("Bank", g("bank")),
            _row("Account Name", g("account_name")),
            _row("Sort Code", g("sort_code")),
            _row("Account Number", g("account_number")),
        ])
    )

    logo = ('<div style="text-align:center;">' + _LOGO_IMG + "</div>") if include_logo else ""
    return (
        '<div style="font-family:Arial,sans-serif;background:#ffffff;padding:20px;color:#334155;">'
        + logo
        + identity
        + accounts_msg
        + payment
        + bank
        + '<div style="text-align:center;font-size:12px;border-top:1px solid #eee;padding-top:20px;margin-top:10px;">'
        '<p style="font-weight:600;">Much appreciated,<br>Nationwide Assist IT / Systems Team</p></div>'
        "</div>"
    )


def send_pay_hirer_email(to: str, subject: str, data: dict, cc: Optional[str] = None) -> dict:
    html = render_pay_hirer(data)
    return send_email(to=to, subject=subject or "Pay Hirer", html=html, cc=cc)
