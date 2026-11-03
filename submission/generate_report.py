from pathlib import Path
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


ROOT = Path(__file__).parent
# Usage: python generate_report.py [source.md] [output.pdf] [footer label]
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "BrandProof_Round2_Report.md"
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else SOURCE.with_suffix(".pdf")
FOOTER = sys.argv[3] if len(sys.argv) > 3 else "BrandProof AI · Round 2 submission"
IS_ROUND2 = "Round2" in SOURCE.name


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
    canvas.drawString(0.65 * inch, 0.35 * inch, FOOTER)
    canvas.drawRightString(7.85 * inch, 0.35 * inch, f"Page {doc.page}")
    canvas.restoreState()


doc = BaseDocTemplate(str(OUTPUT), pagesize=letter, rightMargin=0.65 * inch, leftMargin=0.65 * inch, topMargin=0.62 * inch, bottomMargin=0.72 * inch, title="BrandProof AI Round 2 Report", author="BrandProof AI team")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=footer)])

def markdown_table(rows):
    cells = [[Paragraph(clean(cell.strip()), styles["BPText"]) for cell in row.strip().strip("|").split("|")] for row in rows if not re.match(r"^\s*\|[\s:|-]+\|\s*$", row)]
    width = len(cells[0])
    table = Table(cells, colWidths=[doc.width / width] * width, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9e4ff")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ddd8cf")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


story = []
lines = SOURCE.read_text(encoding="utf-8").splitlines()
table_rows = []
for index, line in enumerate(lines):
    if line.startswith("|"):
        table_rows.append(line)
        if index + 1 >= len(lines) or not lines[index + 1].startswith("|"):
            story.append(markdown_table(table_rows))
            story.append(Spacer(1, 6))
            table_rows = []
        continue
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

if IS_ROUND2:
  story.append(Spacer(1, 10))
  story.append(Paragraph("Verification snapshot", styles["BPH2"]))
  table = Table([
      ["Check", "Result"],
      ["Backend automated tests", "14 passed"],
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
