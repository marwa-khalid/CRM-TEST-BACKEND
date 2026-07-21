"""Vehicle sale documentation: Release of Liability and Sale Receipt.

Both are generated from the purchaser and sale details held on the vehicle
record, as one printable page so preview, print and print-to-PDF all work from
a single view — the same approach as the licensing authority letters.
"""
from datetime import date
from html import escape
from typing import Optional

from fleet.models.tables import FleetVehicleRecord

EM_DASH = "—"


def _fmt_date(value: Optional[date]) -> str:
    return value.strftime("%d/%m/%Y") if value else EM_DASH


def _money(value: Optional[str]) -> str:
    raw = (value or "").strip().replace(",", "").replace("£", "")
    if not raw:
        return EM_DASH
    try:
        return f"£{float(raw):,.2f}"
    except ValueError:
        return value or EM_DASH


def _vehicle_line(record: FleetVehicleRecord) -> str:
    parts = [(record.make or "").strip(), (record.model or "").strip(), (record.variant or "").strip()]
    return " ".join(p for p in parts if p) or EM_DASH


def build_sale_documents_html(record: FleetVehicleRecord) -> str:
    """Release of Liability + Sale Receipt, one per page."""
    today = date.today().strftime("%d %B %Y")
    reg = (record.registration_number or "").strip() or EM_DASH
    vin = (record.chassis_number or "").strip() or EM_DASH
    vehicle = _vehicle_line(record)
    sold_on = _fmt_date(record.vehicle_sold_on)

    purchaser_block = "<br/>".join(
        escape(line) for line in [
            (record.purchaser_name or "").strip(),
            *[p.strip() for p in (record.purchaser_address or "").split(",") if p.strip()],
            (record.purchaser_postcode or "").strip(),
        ] if line
    ) or f'<span class="empty">{EM_DASH}</span>'

    vehicle_rows = f"""
        <tr><th>Registration</th><td>{escape(reg)}</td></tr>
        <tr><th>Vehicle</th><td>{escape(vehicle)}</td></tr>
        <tr><th>Chassis number (VIN)</th><td>{escape(vin)}</td></tr>
        <tr><th>Date of sale</th><td>{escape(sold_on)}</td></tr>"""

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Vehicle Sale Documents</title>
    <style>
      *{{box-sizing:border-box}}
      body{{font-family:Arial,sans-serif;margin:24px;color:#111827;background:#fff}}
      header{{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e5e7eb;padding-bottom:14px;margin-bottom:20px}}
      h1{{font-size:22px;margin:0}}
      h2{{font-size:18px;margin:0 0 14px}}
      button{{font:inherit;border:1px solid #111827;border-radius:4px;background:#111827;color:#fff;padding:10px 14px;cursor:pointer}}
      .doc{{break-after:page;margin-bottom:40px}}
      .doc:last-child{{break-after:auto}}
      .head{{display:flex;justify-content:space-between;gap:24px;margin-bottom:24px}}
      .to,.meta{{line-height:1.5;font-size:13px}}
      .meta{{text-align:right}}
      p{{margin:0 0 10px;line-height:1.5}}
      table{{border-collapse:collapse;width:100%;margin:8px 0 16px}}
      td,th{{border:1px solid #d1d5db;padding:6px 8px;font-size:13px;text-align:left}}
      th{{background:#f3f4f6;width:220px}}
      .sign{{margin-top:36px;display:flex;gap:48px}}
      .sign div{{flex:1;border-top:1px solid #9ca3af;padding-top:6px;font-size:12px;color:#6b7280}}
      .total td{{font-weight:bold}}
      .empty{{color:#9ca3af}}
      @media print{{ body{{margin:0}} header{{display:none}} }}
    </style>
  </head>
  <body>
    <header><h1>Vehicle Sale Documents</h1><button onclick="window.print()">Print</button></header>

    <section class="doc">
      <div class="head">
        <div class="to"><strong>Purchaser</strong><br/>{purchaser_block}</div>
        <div class="meta"><strong>Skyline Car Hire (UK) Ltd</strong><br/>Date: {escape(today)}</div>
      </div>
      <h2>Release of Liability</h2>
      <p>
        Skyline Car Hire (UK) Ltd confirms that ownership of the vehicle described below
        passed to the purchaser named above on {escape(sold_on)}.
      </p>
      <table>{vehicle_rows}</table>
      <p>
        From the date of sale, Skyline Car Hire (UK) Ltd accepts no liability for the vehicle,
        including but not limited to its use, condition, road fund licence, insurance, penalty
        charges or any offence committed in connection with it. The purchaser is responsible
        for notifying the DVLA of the change of keeper.
      </p>
      <div class="sign">
        <div>Signed, for and on behalf of Skyline Car Hire (UK) Ltd</div>
        <div>Signed, purchaser</div>
      </div>
    </section>

    <section class="doc">
      <div class="head">
        <div class="to"><strong>Receipt for</strong><br/>{purchaser_block}</div>
        <div class="meta"><strong>Skyline Car Hire (UK) Ltd</strong><br/>Date: {escape(today)}</div>
      </div>
      <h2>Sale Receipt</h2>
      <table>{vehicle_rows}</table>
      <table>
        <tr><th>Sale price (excluding VAT)</th><td>{escape(_money(record.sold_for_exc_vat))}</td></tr>
        <tr class="total"><th>Sale price (including VAT)</th><td>{escape(_money(record.sold_for_inc_vat))}</td></tr>
      </table>
      <p>Received with thanks.</p>
      <div class="sign">
        <div>Signed, for and on behalf of Skyline Car Hire (UK) Ltd</div>
        <div>Signed, purchaser</div>
      </div>
    </section>
  </body>
</html>"""
