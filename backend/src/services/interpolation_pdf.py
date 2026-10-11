"""Self-contained Unicode PDF: reviewed inputs, monthly plots and monthly tables."""
import math
import sys
import unicodedata
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
INK = colors.HexColor("#18181b")
MUTED = colors.HexColor("#52525b")
BLUE = colors.HexColor("#2563eb")


@lru_cache(maxsize=1)
def registered_fonts():
    for name, filename in (("CortenNoto", "NotoSans.ttf"), ("CortenCJK", "NotoSansSC.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(FONTS / filename)))
    return ("CortenNoto", "CortenCJK")


def markup(text):
    text = unicodedata.normalize("NFC", str(text))
    fonts = registered_fonts()
    chunks, current, buffer = [], None, ""
    for char in text:
        if unicodedata.bidirectional(char) in {"R", "AL"}:
            raise ValueError("PDF export currently supports Chinese, Japanese, Latin, Greek and Cyrillic names. This right-to-left name needs a shaping font; CSV and JSON remain available.")
        font = next((name for name in fonts if pdfmetrics.getFont(name).face.charToGlyph.get(ord(char), 0)), None)
        if font is None:
            raise ValueError(f"PDF font does not support character U+{ord(char):04X}. Rename that header for PDF export; CSV and JSON preserve the original name.")
        if current and current != font:
            chunks.append(f'<font name="{current}">{escape(buffer)}</font>')
            buffer = ""
        current = font
        buffer += char
    if buffer:
        chunks.append(f'<font name="{current}">{escape(buffer)}</font>')
    return "".join(chunks)


def paragraph(text, size=9, color=INK):
    return Paragraph(markup(text), ParagraphStyle("Corten", fontName="CortenNoto", fontSize=size,
                                                leading=size * 1.5, textColor=color, wordWrap="CJK"))


def number(value):
    if value != 0 and (abs(value) >= 1e9 or abs(value) < .005):
        return f"{value:.2e}"
    return f"{value:,.2f}"


class MonthlyPlot(Flowable):
    def __init__(self, result, column, width=745, height=300):
        super().__init__()
        self.result, self.column, self.width, self.height = result, column, width, height

    def draw(self):
        canvas = self.canv
        monthly = [row["values"][self.column] for row in self.result["monthly"]]
        targets = [row["values"][self.column] for row in self.result["yearly"]]
        scale = max(map(abs, monthly + targets)) or 1
        normalized = [value / scale for value in monthly + targets]
        low, high = min(normalized), max(normalized)
        spread = high - low
        if spread == 0:
            spread = .1 * max(abs(high), 1)
        low -= spread * .12
        high += spread * .12
        finite_limit = sys.float_info.max / scale
        low, high = max(low, -finite_limit), min(high, finite_limit)
        left, right, bottom, top = 76, self.width - 16, 42, self.height - 22
        x = lambda index: left + index / max(1, len(monthly) - 1) * (right - left)
        y = lambda value: bottom + ((value / scale) - low) / (high - low) * (top - bottom)
        canvas.setFont("CortenNoto", 8)
        for index in range(5):
            height = bottom + index / 4 * (top - bottom)
            tick = (low + index / 4 * (high - low)) * scale
            canvas.setStrokeColor(colors.HexColor("#e4e4e7"))
            canvas.line(left, height, right, height)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(left - 10, height - 3, f"{tick:.4g}")
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.6)
        path = canvas.beginPath()
        path.moveTo(x(0), y(monthly[0]))
        for index, value in enumerate(monthly[1:], 1):
            path.lineTo(x(index), y(value))
        canvas.drawPath(path)
        canvas.setFillColor(INK)
        stride = max(1, math.ceil(len(targets) / 13))
        for index, target in enumerate(targets):
            anchor = index * 12 + (11 if self.result["mode"] == "exit" else 5.5)
            canvas.circle(x(anchor), y(target), 2.5, stroke=0, fill=1)
            if index % stride == 0 or index == len(targets) - 1:
                canvas.drawCentredString(x(index * 12 + 5.5), bottom - 17, str(self.result["yearly"][index]["year"]))
        canvas.drawCentredString((left + right) / 2, 6, "Year")


def data_table(headers, rows, widths):
    values = [[paragraph(cell, 8) for cell in headers]]
    values += [[paragraph(cell, 8) for cell in row] for row in rows]
    table = Table(values, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f4f5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#d4d4d8")),
    ]))
    return table


def build_pdf(result):
    registered_fonts()
    # Check glyph coverage before building any document. Unsupported scripts
    # must produce a clear error rather than blank squares or altered names.
    for name in result["columns"]:
        markup(name)
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), rightMargin=42, leftMargin=42,
                            topMargin=38, bottomMargin=38, title="Corten yearly-to-monthly review",
                            author="Chryselys Private Limited")
    width = landscape(A4)[0] - 84
    story = [paragraph("Corten | Analyst Workspace", 11, MUTED), Spacer(1, 8),
             paragraph("Yearly-to-monthly interpolation", 22), Spacer(1, 10),
             paragraph(f"{result['mode'].title()} mode · {len(result['yearly'])} years · {len(result['columns'])} independent series", 11),
             Spacer(1, 8), paragraph("All yearly constraints passed on unrounded values. Tables display two decimal places (scientific notation for very large/small values). CSV and JSON contain unrounded monthly values."),
             Spacer(1, 6), paragraph("Average mode uses a soft preference for the input range. Exit mode anchors every December across the full timeline. Only the first month has a sign constraint; other months can fall outside the yearly input range."),
             Spacer(1, 8), paragraph("Input SHA-256: " + result["input_digest"], 7, MUTED),
             paragraph("Calculation: " + result["calculation_id"], 7, MUTED), Spacer(1, 15)]
    for start in range(0, len(result["columns"]), 4):
        indices = list(range(start, min(start + 4, len(result["columns"]))))
        story += [paragraph("Yearly input", 14), Spacer(1, 8),
                  data_table(["Year", *[result["columns"][i] for i in indices]],
                             [[row["year"], *[number(row["values"][i]) + result["units"][i] for i in indices]] for row in result["yearly"]],
                             [60] + [(width - 60) / len(indices)] * len(indices)), Spacer(1, 12)]
    for column, series in enumerate(result["series"]):
        story += [PageBreak(), paragraph(series["name"], 18), Spacer(1, 8),
                  paragraph("Blue: monthly values. Black markers: " + ("December targets." if result["mode"] == "exit" else "yearly average targets, positioned at mid-year.")),
                  MonthlyPlot(result, column, width, 285),
                  paragraph(f"Input range: {number(series['input_min'])} to {number(series['input_max'])}. Monthly range: {number(series['monthly_min'])} to {number(series['monthly_max'])}. {series['outside_range_months']} months outside the input range."),
                  paragraph("First month (unrounded): " + repr(series["first_month"]), 9),
                  paragraph("Every yearly mean matches its target." if result["mode"] == "average" else "Every December matches its target.", 9)]
    for start in range(0, len(result["columns"]), 4):
        indices = list(range(start, min(start + 4, len(result["columns"]))))
        story += [PageBreak(), paragraph("Monthly output", 16), Spacer(1, 8),
                  data_table(["Year", "Month", *[result["columns"][i] for i in indices]],
                             [[row["year"], row["month"], *[number(row["values"][i]) + result["units"][i] for i in indices]] for row in result["monthly"]],
                             [50, 50] + [(width - 100) / len(indices)] * len(indices))]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("CortenNoto", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(42, 20, "Chryselys Private Limited · Yearly-to-monthly review")
        canvas.drawRightString(landscape(A4)[0] - 42, 20, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
