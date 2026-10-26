from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


ROOT = Path(__file__).parent
SOURCE = ROOT / "BrandProof_Round2_Report.md"
OUTPUT = ROOT / "BrandProof_Round2_Report.pdf"


def clean(text: str) -> str:
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    return text


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BPTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=colors.HexColor("#182136"), spaceAfter=8))
styles.add(ParagraphStyle(name="BPSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=12, leading=17, textColor=colors.HexColor("#6f4bf2"), spaceAfter=18))
styles.add(ParagraphStyle(name="BPH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=20, textColor=colors.HexColor("#182136"), spaceBefore=16, spaceAfter=7))
styles.add(ParagraphStyle(name="BPText", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=14, textColor=colors.HexColor("#424b5e"), spaceAfter=7))
styles.add(ParagraphStyle(name="BPBullet", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.3, leading=13, leftIndent=16, firstLineIndent=-9, bulletIndent=4, textColor=colors.HexColor("#424b5e"), spaceAfter=4))
styles.add(ParagraphStyle(name="BPNote", parent=styles["BodyText"], fontName="Helvetica-Oblique", fontSize=8.5, leading=12, textColor=colors.HexColor("#6b7280"), backColor=colors.HexColor("#f1edff"), borderPadding=9, spaceBefore=6, spaceAfter=10))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#e7e3dc"))
    canvas.line(0.65 * inch, 0.55 * inch, 7.85 * inch, 0.55 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#8a90a0"))
    canvas.drawString(0.65 * inch, 0.35 * inch, "BrandProof AI · Round 2 submission")
    canvas.drawRightString(7.85 * inch, 0.35 * inch, f"Page {doc.page}")
    canvas.restoreState()


doc = BaseDocTemplate(str(OUTPUT), pagesize=letter, rightMargin=0.65 * inch, leftMargin=0.65 * inch, topMargin=0.62 * inch, bottomMargin=0.72 * inch, title="BrandProof AI Round 2 Report", author="BrandProof AI team")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=footer)])

story = []
lines = SOURCE.read_text(encoding="utf-8").splitlines()
for index, line in enumerate(lines):
    if line.startswith("# "):
        story.append(Paragraph(clean(line[2:]), styles["BPTitle"]))
        story.append(Spacer(1, 2))
    elif line.startswith("## "):
        story.append(Paragraph(clean(line[3:]), styles["BPH2"]))
    elif line.startswith("### "):
        story.append(Paragraph(clean(line[4:]), styles["BPH2"]))
    elif line.startswith("- "):
        story.append(Paragraph(clean(line[2:]), styles["BPBullet"], bulletText="•"))
    elif line.startswith("**") and line.endswith("**"):
        story.append(Paragraph(clean(line), styles["BPSubtitle"]))
    elif line.startswith("The product is implemented") or line.startswith("Browser screenshot"):
        story.append(Paragraph(clean(line), styles["BPNote"]))
    elif line.strip():
        story.append(Paragraph(clean(line), styles["BPText"]))

story.append(Spacer(1, 10))
story.append(Paragraph("Verification snapshot", styles["BPH2"]))
table = Table([
    ["Check", "Result"],
    ["Backend automated tests", "6 passed"],
    ["Python compile check", "Passed"],
    ["Frontend TypeScript", "Passed"],
    ["Next.js production build", "Passed"],
    ["Live API smoke check", "HTTP 200"],
    ["Docker / browser capture", "Environment unavailable"],
], colWidths=[3.55 * inch, 3.65 * inch])
table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#202942")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("LEADING", (0, 0), (-1, -1), 10),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ddd8cf")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fffdf9"), colors.HexColor("#f7f4ee")]),
    ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#424b5e")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(table)
doc.build(story)
print(OUTPUT)
