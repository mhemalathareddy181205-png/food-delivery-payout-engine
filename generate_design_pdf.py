"""Render docs/design.md as a readable PDF using the installed ReportLab package."""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "docs" / "design.md"
TARGET = ROOT / "docs" / "design.pdf"

def pdf_text(text):
    # Built-in PDF fonts use WinAnsi; replace unsupported characters cleanly.
    return escape(text.replace("—", "-").replace("–", "-").replace("’", "'"))

def build():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#17324D"), spaceAfter=12))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#245B83"), spaceBefore=11, spaceAfter=5))
    styles.add(ParagraphStyle(name="BodyReadable", parent=styles["BodyText"], leading=14, spaceAfter=6))
    styles.add(ParagraphStyle(name="CodeLine", parent=styles["BodyText"], fontName="Courier", fontSize=8.5, leading=11, leftIndent=12, spaceAfter=3))
    story=[]; bullets=[]; in_code=False
    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        line=raw.rstrip()
        if line.startswith("```"):
            if bullets:
                story.append(ListFlowable([ListItem(Paragraph(pdf_text(x),styles["BodyReadable"])) for x in bullets],bulletType="bullet",leftIndent=18)); bullets=[]
            in_code=not in_code; continue
        if in_code:
            story.append(Paragraph(pdf_text(line or " "),styles["CodeLine"])); continue
        if line.startswith("- ") or (len(line)>2 and line[0].isdigit() and line[1:3]==". "):
            bullets.append(line[2:] if line.startswith("- ") else line[3:]); continue
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(pdf_text(x),styles["BodyReadable"])) for x in bullets],bulletType="bullet",leftIndent=18)); bullets=[]
        if not line:
            story.append(Spacer(1,3)); continue
        if line.startswith("# "):
            story.append(Paragraph(pdf_text(line[2:]),styles["DocTitle"]))
        elif line.startswith("## "):
            story.append(Paragraph(pdf_text(line[3:]),styles["Section"]))
        else:
            story.append(Paragraph(pdf_text(line.replace("`", "")),styles["BodyReadable"]))
    if bullets:
        story.append(ListFlowable([ListItem(Paragraph(pdf_text(x),styles["BodyReadable"])) for x in bullets],bulletType="bullet",leftIndent=18))
    doc=SimpleDocTemplate(str(TARGET),pagesize=A4,rightMargin=20*mm,leftMargin=20*mm,topMargin=18*mm,bottomMargin=18*mm,title="PS-039 Food Delivery Settlement Engine Design")
    doc.build(story)
    return TARGET

if __name__=="__main__":
    print(build())
