import io
import os
import tempfile
import uuid
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# def utc_now():
#     return datetime.now(timezone.utc)

# PNG renders generated from the same frontend SVGs imported by AIReportSlider.
# ReportLab's SVG parser cannot faithfully handle these Figma pattern fills.
_LOCATION_IMG_FILES = {
    "Front":            "Group.png",
    "Rear":             "Group-1.png",
    "Roof":             "Group-2.png",
    "Nearside Front":   "Group-3.png",
    "Nearside Middle":  "Group-4.png",
    "Nearside Rear":    "Group-5.png",
    "Offside Front":    "Group-6.png",
    "Offside Middle":   "Group-7.png",
    "Offside Rear":     "Group-8.png",
}

_LOCATION_ORDER = list(_LOCATION_IMG_FILES.keys())

# Point this at the rendered vehicle-location PNG folder on the backend.
# Black = client vehicle, Red = third party vehicle (mirrors the Black/ and Red/
# car SVG sets on the frontend manual-damage screen).
_DEFAULT_IMG_DIR = os.environ.get(
    "VEHICLE_LOCATION_IMG_DIR",
    str(Path(__file__).resolve().parent.parent / "assets" / "vehicle_location_renders"),
)
_DEFAULT_IMG_DIR_RED = os.environ.get(
    "VEHICLE_LOCATION_IMG_DIR_RED",
    str(Path(__file__).resolve().parent.parent / "assets" / "vehicle_location_renders_red"),
)

class AIReportPDFService:
    # ------------------------------------------------------------------ utils
    @staticmethod
    def generate_report_id() -> str:
        return f"RPT-{datetime.utcnow().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"

    @staticmethod
    def get_suggested_repair(damage_type: str) -> str:
        dt = (damage_type or "").strip().lower()
        if dt == "dent":
            return "Repair & paint"
        if dt == "broken":
            return "Replace part"
        if dt == "crash":
            return "Replace or major repair"
        if dt == "scratch":
            return "Paint / polish"
        if dt == "shattered":
            return "Replace glass"
        return "Inspect"

    @staticmethod
    def _safe_str(value: Any, default: str = "-") -> str:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    @staticmethod
    def _format_generated_date(generated_at: Optional[str] = None) -> str:
        if generated_at:
            try:
                parsed = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
                return parsed.strftime("%d %b %Y, %H:%M")
            except Exception:
                return str(generated_at)
        return datetime.utcnow().strftime("%d %b %Y, %H:%M") + " UTC"

    @staticmethod
    def _severity_counts(predictions: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"High": 0, "Medium": 0, "Low": 0}
        for item in predictions or []:
            sev = (item.get("severity") or "").strip().capitalize()
            if sev in counts:
                counts[sev] += 1
        return counts

    @staticmethod
    def _location_counts(predictions: List[Dict[str, Any]]) -> Dict[str, int]:
        counter = Counter(
            (item.get("side") or item.get("damage_side") or "").strip()
            for item in (predictions or [])
        )
        return {name: counter.get(name, 0) for name in _LOCATION_ORDER}

    @staticmethod
    def _download_image_to_temp(image_url: Optional[str]) -> Optional[str]:
        if not image_url:
            return None
        try:
            import requests
            response = requests.get(image_url, timeout=20)
            response.raise_for_status()
            suffix = ".png"
            ctype = response.headers.get("Content-Type", "").lower()
            if "jpeg" in ctype or "jpg" in ctype:
                suffix = ".jpg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(response.content)
                return tmp.name
        except Exception:
            return None

    # ------------------------------------------------------------------ styles
    @staticmethod
    def _build_styles():
        styles = getSampleStyleSheet()

        def add(name, **kw):
            if name in styles.byName:
                return
            styles.add(ParagraphStyle(name=name, **kw))

        add("TitleMain", fontName="Helvetica-Bold", fontSize=18, leading=22,
            textColor=colors.HexColor("#111827"), alignment=TA_LEFT)
        add("SectionTitle", fontName="Helvetica-Bold", fontSize=13, leading=16,
            textColor=colors.HexColor("#111827"), alignment=TA_LEFT, spaceAfter=6)
        add("Meta", fontName="Helvetica", fontSize=9, leading=12,
            textColor=colors.HexColor("#4B5563"))
        add("SmallMuted", fontName="Helvetica", fontSize=8, leading=11,
            textColor=colors.HexColor("#6B7280"))
        add("Card", fontName="Helvetica", fontSize=9, leading=12,
            alignment=TA_LEFT, textColor=colors.HexColor("#374151"))
        add("LocationLabel", fontName="Helvetica", fontSize=9, leading=11,
            alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"))
        add("LocationCount", fontName="Helvetica-Bold", fontSize=18, leading=20,
            alignment=TA_CENTER, textColor=colors.HexColor("#111827"))
        return styles

    # ------------------------------------------------------------------ blocks
    @staticmethod
    def _build_meta_table(styles, claim_reference, report_id, generated_at, assessment_type):
        cell = lambda label, value: Paragraph(
            f'<font color="#6B7280">{label}:</font> '
            f'<font color="#111827"><b>{value}</b></font>',
            styles["Meta"],
        )
        data = [
            [cell("Claim ID", claim_reference), cell("Report ID", report_id)],
            [cell("Generated", generated_at), cell("Assessment Type", assessment_type)],
        ]
        t = Table(data, colWidths=[90 * mm, 90 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#d9ebff")),  # app blue-100
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#a2cfff")),    # app blue-200
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#a2cfff")),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    @staticmethod
    def _build_image_gallery(styles, images: List[Dict[str, Any]], temp_paths: List[str]):
        cells = []
        for image in images or []:
            url = image.get("annotated_image_url") or image.get("original_image_url") or ""
            if not url:
                cells.append(Paragraph("No image", styles["Meta"]))
                continue

            temp_path = AIReportPDFService._download_image_to_temp(url)
            if temp_path and os.path.exists(temp_path):
                temp_paths.append(temp_path)
                try:
                    cells.append(Image(temp_path, width=27 * mm, height=22 * mm))
                except Exception:
                    cells.append(Paragraph("Image failed", styles["Meta"]))
            else:
                cells.append(Paragraph("No image", styles["Meta"]))

        if not cells:
            return Paragraph("No images available", styles["Meta"])

        rows = []
        for i in range(0, len(cells), 6):
            row = cells[i:i + 6]
            while len(row) < 6:
                row.append("")
            rows.append(row)

        table = Table(rows, colWidths=[29 * mm] * 6, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E5E7EB")),
            ("INNERGRID", (0, 0), (-1, -1), 4, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    @staticmethod
    def _build_damage_table(styles, predictions: List[Dict[str, Any]]):
        headers = [
            "DAMAGE SIDE", "AREA OF DAMAGE", "TYPE OF DAMAGE",
            "SEVERITY", "CONFIDENCE", "POINTS", "SUGGESTED REPAIR",
        ]
        rows = [headers]

        if predictions:
            for item in predictions:
                conf_raw = item.get("confidence", 0) or 0
                try:
                    conf_val = float(conf_raw)
                except (TypeError, ValueError):
                    conf_val = 0.0
                if conf_val <= 1:
                    conf_val *= 100
                conf_text = f"{round(conf_val)}%"

                damage_type = item.get("damage_type") or item.get("type_of_damage") or item.get("type") or "-"
                rows.append([
                    AIReportPDFService._safe_str(item.get("side") or item.get("damage_side")),
                    AIReportPDFService._safe_str(item.get("part") or item.get("area_of_damage") or item.get("area")),
                    AIReportPDFService._safe_str(damage_type),
                    AIReportPDFService._safe_str(item.get("severity")).capitalize(),
                    conf_text,
                    str(item.get("points", 1)),
                    AIReportPDFService._safe_str(
                        item.get("suggested_repair") or item.get("repair") or AIReportPDFService.get_suggested_repair(damage_type)
                    ),
                ])
        else:
            rows.append(["No damages found", "-", "-", "-", "-", "-", "-"])

        col_widths = [22 * mm, 30 * mm, 26 * mm, 20 * mm, 22 * mm, 16 * mm, 44 * mm]
        t = Table(rows, colWidths=col_widths, repeatRows=1)

        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.white),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#E5E7EB")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E5E7EB")),
            ("INNERGRID", (0, 1), (-1, -1), 0.4, colors.HexColor("#F3F4F6")),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#374151")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]

        for r in range(1, len(rows)):
            sev = str(rows[r][3]).strip().lower()
            if sev == "high":
                style_cmds.append(("BACKGROUND", (3, r), (3, r), colors.HexColor("#FEE2E2")))  # red-100
                style_cmds.append(("TEXTCOLOR", (3, r), (3, r), colors.HexColor("#B91C1C")))    # red-700
            elif sev == "medium":
                style_cmds.append(("BACKGROUND", (3, r), (3, r), colors.HexColor("#FFEDD5")))  # orange-100
                style_cmds.append(("TEXTCOLOR", (3, r), (3, r), colors.HexColor("#F97316")))    # orange-500
            elif sev == "low":
                style_cmds.append(("BACKGROUND", (3, r), (3, r), colors.HexColor("#DCFCE7")))  # green-100
                style_cmds.append(("TEXTCOLOR", (3, r), (3, r), colors.HexColor("#22C55E")))    # green-500

        t.setStyle(TableStyle(style_cmds))
        return t

    @staticmethod
    def _build_stat_cards(styles, total, high, medium, low):
        cards = [
            ("#E5E7EB", "Total Damages",   total),
            ("#EF4444", "High Severity",   high),
            ("#FB923C", "Medium Severity", medium),
            ("#22C55E", "Low Severity",    low),
        ]
        data = [[
            Paragraph(
                f'<font size="18" color="#111827"><b>{count}</b></font><br/><br/>'
                f'<font size="9" color="#6B7280">{label}</font>',
                styles["Card"],
            )
            for _, label, count in cards
        ]]
        t = Table(data, colWidths=[45 * mm, 45 * mm, 45 * mm, 45 * mm])
        style_cmds = [
            ("INNERGRID", (0, 0), (-1, -1), 8, colors.white),   # spacing between cards
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        # Per-card full border in its own color
        for idx, (hex_color, _, _) in enumerate(cards):
            style_cmds.append(("BOX", (idx, 0), (idx, 0), 1.2, colors.HexColor(hex_color)))
        t.setStyle(TableStyle(style_cmds))
        return t
    # ----------------------------------------------------------- location grid
    @staticmethod
    def _load_location_image(location_key: str, width_mm: float, height_mm: float, red: bool = False):
        filename = _LOCATION_IMG_FILES.get(location_key)
        if not filename:
            return Spacer(1, height_mm * mm)

        base_dir = _DEFAULT_IMG_DIR_RED if red else _DEFAULT_IMG_DIR
        full_path = Path(base_dir) / filename
        # Fall back to the black render if a red one is missing, so the grid
        # never renders empty.
        if red and not full_path.exists():
            full_path = Path(_DEFAULT_IMG_DIR) / filename
        if not full_path.exists():
            return Spacer(1, height_mm * mm)

        try:
            target_w = width_mm * mm
            target_h = height_mm * mm
            img = Image(
                str(full_path),
                width=target_w,
                height=target_h,
                kind="proportional",
                mask="auto",
            )
            img.hAlign = "CENTER"
            return img
        except Exception:
            return Spacer(1, height_mm * mm)
    @staticmethod
    def _build_location_cell(styles, count: int, location_key: str, red: bool = False):
        """Builds a clean cell mimicking your UI cards: count, clean car asset, label."""
        cell_items: List[Any] = []
        cell_items.append(Paragraph(str(count), styles["LocationCount"]))
        cell_items.append(Spacer(1, 4))

        img_widget = AIReportPDFService._load_location_image(location_key, width_mm=32, height_mm=18, red=red)
        cell_items.append(img_widget)

        cell_items.append(Spacer(1, 4))
        cell_items.append(Paragraph(location_key, styles["LocationLabel"]))
        return cell_items

    @staticmethod
    def _build_location_grid(styles, location_counts: Dict[str, int], red: bool = False):
        rows_layout = [
            ["Front", "Rear", "Roof"],
            ["Nearside Front", "Nearside Middle", "Nearside Rear"],
            ["Offside Front", "Offside Middle", "Offside Rear"],
        ]
        table_rows = []
        for row in rows_layout:
            table_rows.append([
                AIReportPDFService._build_location_cell(styles, location_counts.get(key, 0), key, red=red)
                for key in row
            ])

        col_w = 55 * mm
        row_h = 36 * mm # Slightly widened to cushion the bounding box cleanly
        t = Table(
            table_rows,
            colWidths=[col_w, col_w, col_w],
            rowHeights=[row_h, row_h, row_h],
        )
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E5E7EB")),
            ("INNERGRID", (0, 0), (-1, -1), 6, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        return t

    # ---------------------------------------------------------------- audit
    @staticmethod
    def _build_audit_table(audit_trail: List[Dict[str, Any]]):
        data = [["DONE BY", "ACTION", "TIMESTAMP"]]
        for item in audit_trail or []:
            data.append([
                AIReportPDFService._safe_str(item.get("doneBy") or item.get("done_by")),
                AIReportPDFService._safe_str(item.get("action")),
                AIReportPDFService._format_generated_date(item.get("timestamp")),
            ])
        if len(data) == 1:
            data.append(["-", "-", "-"])

        t = Table(data, colWidths=[55 * mm, 80 * mm, 45 * mm])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E5E7EB")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#E5E7EB")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#4B5563")),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        return t

    # ----------------------------------------------------------- vehicle cards
    @staticmethod
    def _vehicle_text(v: Optional[Dict[str, Any]]) -> str:
        if not v:
            return "-"
        reg = v.get("registration") or "-"
        tail = ", ".join([str(x) for x in [
            " ".join([str(p) for p in [v.get("make"), v.get("model")] if p]),
            v.get("year"),
            v.get("color") or v.get("colour"),
        ] if x])
        return f"{reg}, {tail}" if tail else str(reg)

    @staticmethod
    def _build_vehicle_cards(styles, client_vehicle, third_party_vehicle, assessment_type):
        show_client = assessment_type != "Third Party Vehicle Only"
        show_tp = assessment_type in ("Both", "Third Party Vehicle Only")
        cells = []
        if show_client:
            cells.append(("Client Vehicle", AIReportPDFService._vehicle_text(client_vehicle), "client"))
        if show_tp:
            cells.append(("Third party Vehicle", AIReportPDFService._vehicle_text(third_party_vehicle), "tp"))
        if not cells:
            return Spacer(1, 0)

        row = [
            Paragraph(
                f'<font size="13" color="#000000"><b>{title}</b></font><br/><br/>'
                f'<font size="9" color="#374151">Reg# </font>'
                f'<font size="9" color="#374151"><b>{text}</b></font>',
                styles["Card"],
            )
            for title, text, _ in cells
        ]
        col_w = (90 * mm) if len(row) == 2 else (180 * mm)
        t = Table([row], colWidths=[col_w] * len(row))
        style_cmds = [
            ("INNERGRID", (0, 0), (-1, -1), 8, colors.white),  # gap between cards
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]
        for idx, (_, _, kind) in enumerate(cells):
            if kind == "client":
                style_cmds.append(("BACKGROUND", (idx, 0), (idx, 0), colors.HexColor("#d9ebff")))  # blue-100
            else:
                style_cmds.append(("BACKGROUND", (idx, 0), (idx, 0), colors.white))
                style_cmds.append(("BOX", (idx, 0), (idx, 0), 1.0, colors.HexColor("#a2cfff")))    # blue-200
        t.setStyle(TableStyle(style_cmds))
        return t

    @staticmethod
    def _build_single_vehicle_card(styles, title: str, vehicle: Optional[Dict[str, Any]], kind: str):
        """One vehicle card (client = blue fill, third party = red outline)."""
        para = Paragraph(
            f'<font size="13" color="#000000"><b>{title}</b></font><br/><br/>'
            f'<font size="9" color="#374151">Reg# </font>'
            f'<font size="9" color="#374151"><b>{AIReportPDFService._vehicle_text(vehicle)}</b></font>',
            styles["Card"],
        )
        t = Table([[para]], colWidths=[180 * mm])
        style_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]
        if kind == "client":
            style_cmds.append(("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#d9ebff")))  # blue-100
            style_cmds.append(("BOX", (0, 0), (0, 0), 1.0, colors.HexColor("#a2cfff")))     # blue-200
        else:
            style_cmds.append(("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FEECEC")))   # red-50
            style_cmds.append(("BOX", (0, 0), (0, 0), 1.0, colors.HexColor("#F1A9A9")))     # red-300
        t.setStyle(TableStyle(style_cmds))
        return t

    # ----------------------------------------------------------- manual adjustments
    @staticmethod
    def _boxed_value(styles, text: str):
        t = Table([[Paragraph(AIReportPDFService._safe_str(text), styles["Card"])]], colWidths=[180 * mm])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E1DFDD")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        return t

    @staticmethod
    def _build_manual_adjustments(styles, predictions, manual_adjustments):
        ma = manual_adjustments or {}
        decisions = ma.get("decisions") or {}
        notes = ma.get("notes") or ""
        vehicle_status = ma.get("vehicleStatus") or ma.get("vehicle_status") or "Roadworthy"

        items = []
        if predictions and decisions:
            rows = []
            for idx, det in enumerate(predictions):
                code = f"DMG-{idx + 1:03d}"
                label = " - ".join([str(x) for x in [
                    det.get("side") or det.get("damage_side"),
                    det.get("part") or det.get("area_of_damage") or det.get("area"),
                ] if x])
                dtype = det.get("damage_type") or det.get("type_of_damage") or det.get("type") or "-"
                det_id = det.get("detection_id") or f"{det.get('class')}-{idx}"
                decision = decisions.get(det_id) or decisions.get(str(idx)) or ""
                if decision == "accepted":
                    tag = '<font color="#22C55E"><b>Accepted</b></font>'
                elif decision == "rejected":
                    tag = '<font color="#EF4444"><b>Rejected</b></font>'
                else:
                    tag = "-"
                rows.append([
                    Paragraph(f'{code} {label} &nbsp; <font color="#286CFF">[{dtype}]</font>', styles["Card"]),
                    Paragraph(tag, styles["Card"]),
                ])
            t = Table(rows, colWidths=[140 * mm, 40 * mm])
            t.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E1DFDD")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#F3F4F6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            items.append(t)
        else:
            items.append(Paragraph("No manual adjustment data available from source report", styles["SmallMuted"]))

        items.append(Spacer(1, 10))
        items.append(Paragraph('<font color="#374151"><b>Additional Notes / Unrelated Damage</b></font>', styles["Meta"]))
        items.append(Spacer(1, 3))
        items.append(AIReportPDFService._boxed_value(styles, notes))
        items.append(Spacer(1, 10))
        items.append(Paragraph('<font color="#374151"><b>Vehicle Status</b></font>', styles["Meta"]))
        items.append(Spacer(1, 3))
        items.append(AIReportPDFService._boxed_value(styles, vehicle_status))
        return items

    # =================================================================
    # PUBLIC ENTRY POINT
    # =================================================================
    @staticmethod
    def build_collective_pdf_bytes(
        claim_reference: str,
        images: List[Dict[str, Any]],
        predictions: List[Dict[str, Any]],
        report_id: Optional[str] = None,
        generated_at: Optional[str] = None,
        uploaded_by: str = "Client",
        source_name: str = "Claim Portal",
        assessment_type: str = "-",
        audit_trail: Optional[List[Dict[str, Any]]] = None,
        client_vehicle: Optional[Dict[str, Any]] = None,
        third_party_vehicle: Optional[Dict[str, Any]] = None,
        manual_adjustments: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=14 * mm,
            leftMargin=14 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="AI Vehicle Damage Full Report",
        )

        styles = AIReportPDFService._build_styles()
        generated_text = AIReportPDFService._format_generated_date(generated_at)
        report_id_text = report_id or AIReportPDFService.generate_report_id()
        claim_reference = AIReportPDFService._safe_str(claim_reference)
        assessment_type = AIReportPDFService._safe_str(assessment_type)

        severity_counts = AIReportPDFService._severity_counts(predictions)
        total_damages = len(predictions or [])
        location_counts = AIReportPDFService._location_counts(predictions)

        image_count = len(images or [])
        if image_count == 1:
            file_name_list = images[0].get("original_filename") or images[0].get("file_name") or "Uploaded image"
        else:
            file_name_list = f"{image_count} uploaded images"

        if not audit_trail:
            audit_trail = [{
                "doneBy": uploaded_by or "System",
                "action": "Generated Collective AI Report",
                "timestamp": generated_at or datetime.utcnow().isoformat(),
            }]

        story = []
        temp_paths: List[str] = []

        # ----- Header
        story.append(Paragraph("AI Vehicle Damage Full Report", styles["TitleMain"]))
        story.append(Spacer(1, 8))
        story.append(AIReportPDFService._build_meta_table(
            styles, claim_reference, report_id_text, generated_text, assessment_type,
        ))
        story.append(Spacer(1, 6))

        meta_line = (
            f'Uploaded By: <font color="#0352FD"><b>{uploaded_by}</b></font>'
            f'&nbsp;&nbsp;•&nbsp;&nbsp; File Name: <b>{file_name_list}</b>'
            f'&nbsp;&nbsp;•&nbsp;&nbsp; Source: <b>{source_name}</b>'
        )
        story.append(Paragraph(meta_line, styles["SmallMuted"]))
        story.append(Spacer(1, 14))

        # ----- Per-vehicle sections (Client vehicle in black, Third party in red).
        # Each vehicle repeats the same order: card, Damage Summary, Images,
        # Damage By Severity, Damage By Location. Split images/predictions by the
        # `vehicle_type` tag stamped at analysis time.
        def _subset(items, vt):
            if vt == "client":
                return [it for it in (items or []) if (it.get("vehicle_type") or "client") == "client"]
            return [it for it in (items or []) if it.get("vehicle_type") == "third_party"]

        at = (assessment_type or "").strip().lower()
        if at == "third party vehicle only":
            vehicle_sections = [("third_party", "Third Party Vehicle", third_party_vehicle, True)]
        elif at == "both":
            vehicle_sections = [
                ("client", "Client Vehicle", client_vehicle, False),
                ("third_party", "Third Party Vehicle", third_party_vehicle, True),
            ]
        else:
            vehicle_sections = [("client", "Client Vehicle", client_vehicle, False)]

        for sec_idx, (vt, title, veh, is_red) in enumerate(vehicle_sections):
            v_images = _subset(images, vt)
            v_preds = _subset(predictions, vt)
            v_sev = AIReportPDFService._severity_counts(v_preds)
            v_loc = AIReportPDFService._location_counts(v_preds)

            # Start the third party (and any later) vehicle on a fresh page.
            if sec_idx > 0:
                story.append(PageBreak())

            # Vehicle card / heading
            story.append(AIReportPDFService._build_single_vehicle_card(
                styles, title, veh, "client" if vt == "client" else "tp",
            ))
            story.append(Spacer(1, 12))

            # Damage Summary
            story.append(Paragraph("Damage Summary", styles["SectionTitle"]))
            story.append(AIReportPDFService._build_damage_table(styles, v_preds))
            story.append(Spacer(1, 14))

            # Images with AI Detection
            story.append(Paragraph("Images with AI Detection", styles["SectionTitle"]))
            story.append(Paragraph(
                f"{len(v_images)} image{'s' if len(v_images) != 1 else ''} • Uploaded",
                styles["SmallMuted"],
            ))
            story.append(Spacer(1, 6))
            story.append(AIReportPDFService._build_image_gallery(styles, v_images, temp_paths))
            story.append(Spacer(1, 8))
            story.append(Paragraph(
                f'<font color="#DC2626">●</font> High Severity ({v_sev["High"]}) &nbsp;&nbsp;&nbsp;'
                f'<font color="#F97316">●</font> Medium Severity ({v_sev["Medium"]}) &nbsp;&nbsp;&nbsp;'
                f'<font color="#16A34A">●</font> Low Severity ({v_sev["Low"]})',
                styles["Meta"],
            ))
            story.append(Spacer(1, 14))

            # Damage By Severity
            story.append(KeepTogether([
                Paragraph("Damage By Severity", styles["SectionTitle"]),
                AIReportPDFService._build_stat_cards(
                    styles,
                    total=len(v_preds),
                    high=v_sev["High"],
                    medium=v_sev["Medium"],
                    low=v_sev["Low"],
                ),
            ]))
            story.append(Spacer(1, 14))

            # Damage By Location (red car diagrams for the third party vehicle)
            story.append(KeepTogether([
                Paragraph("Damage By Location", styles["SectionTitle"]),
                AIReportPDFService._build_location_grid(styles, v_loc, red=is_red),
            ]))
            story.append(Spacer(1, 14))

        # ----- Section: Manual Adjustments (applies to the whole report)
        story.append(Paragraph("Manual Adjustments", styles["SectionTitle"]))
        for _el in AIReportPDFService._build_manual_adjustments(styles, predictions or [], manual_adjustments):
            story.append(_el)
        story.append(Spacer(1, 14))

        # ----- Section: Audit Trail
        story.append(KeepTogether([
            Paragraph("Audit Trail", styles["SectionTitle"]),
            AIReportPDFService._build_audit_table(audit_trail),
        ]))

        doc.build(story)

        # Cleanup downloaded temp files
        for path in temp_paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
