"""Generate the clean NovaGear demo PDFs.

The org chart describes people and responsibilities only. It never states the
purchase flow or the approval thresholds, so the AI has to discover the
workflow from the purchasing policy. The word "Director" appears only in the
policy: the org chart has no such role, which the demo relies on.

Run: uv run python scripts/make_demo_pdfs.py
"""

import shutil
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "demo_assets" / "en"
WEB_DIR = ROOT / "web" / "public" / "demo"

INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5B6770")
RULE = colors.HexColor("#C9D1D6")
HEAD_FILL = colors.HexColor("#EEF2F4")

TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=INK)
SUBTITLE = ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10, leading=14, textColor=MUTED)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=INK,
                    spaceBefore=14, spaceAfter=6)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14, textColor=INK)
FOOT = ParagraphStyle("foot", fontName="Helvetica-Oblique", fontSize=8, leading=11, textColor=MUTED)

FOOTNOTE = "NovaGear Inc. is a fictional company. This document is sample data."

# (department, head role, team role)
DEPARTMENTS = [
    ("Sales", "Sales Manager", "Sales Representative"),
    ("Operations", "Operations Manager", "Operations Specialist"),
    ("Finance", "Finance Manager", "Accountant"),
    ("Procurement", "Procurement Manager", "Procurement Specialist"),
]

RESPONSIBILITIES = [
    ("Chief Executive Officer (CEO)", "Sets company strategy and leads the management team."),
    ("Sales Manager", "Leads the sales team and key customer accounts."),
    ("Sales Representative", "Sells products and manages customer relationships."),
    ("Operations Manager", "Approves departmental purchase needs and business necessity."),
    ("Operations Specialist", "Submits operational purchase requests."),
    ("Finance Manager", "Validates amounts, policy rules, and required approvals."),
    ("Accountant", "Validates amounts, policy rules, and required approvals."),
    ("Procurement Manager", "Selects vendors and executes approved purchases."),
    ("Procurement Specialist", "Selects vendors and executes approved purchases."),
]

APPROVAL_RULES = [
    ("Below USD 1,000", "Manager approval"),
    ("USD 1,000 - USD 5,000", "Manager approval + Finance validation"),
    ("Above USD 5,000", "Manager approval + Finance validation + Director approval"),
]


def grid_table(rows, col_widths):
    """A plain table whose cells never wrap, so PDF text extraction keeps each row on one line."""
    table = Table(rows, colWidths=col_widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_FILL),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def org_tree() -> Drawing:
    """CEO on top, one column per department with its head and team role."""
    width, height = 495, 150
    d = Drawing(width, height)
    box_w, box_h = 112, 26
    ceo_x = (width - 150) / 2
    d.add(Rect(ceo_x, 118, 150, 30, fillColor=HEAD_FILL, strokeColor=INK, strokeWidth=0.8))
    d.add(String(ceo_x + 75, 134, "Chief Executive Officer", fontName="Helvetica-Bold", fontSize=9,
                 textAnchor="middle", fillColor=INK))
    d.add(String(ceo_x + 75, 123, "Alex Morgan", fontName="Helvetica", fontSize=8,
                 textAnchor="middle", fillColor=MUTED))
    d.add(Line(width / 2, 118, width / 2, 104, strokeColor=INK, strokeWidth=0.8))

    gap = (width - 4 * box_w) / 3
    centers = [box_w / 2 + i * (box_w + gap) for i in range(4)]
    d.add(Line(centers[0], 104, centers[-1], 104, strokeColor=INK, strokeWidth=0.8))
    for cx, (dept, head, team) in zip(centers, DEPARTMENTS):
        d.add(Line(cx, 104, cx, 92, strokeColor=INK, strokeWidth=0.8))
        d.add(String(cx, 95 - 12, dept.upper(), fontName="Helvetica-Bold", fontSize=7,
                     textAnchor="middle", fillColor=MUTED))
        d.add(Rect(cx - box_w / 2, 48, box_w, box_h, fillColor=colors.white, strokeColor=INK,
                   strokeWidth=0.8))
        d.add(String(cx, 58, head, fontName="Helvetica-Bold", fontSize=8, textAnchor="middle",
                     fillColor=INK))
        d.add(Line(cx, 48, cx, 34, strokeColor=INK, strokeWidth=0.8))
        d.add(Rect(cx - box_w / 2, 8, box_w, box_h, fillColor=colors.white, strokeColor=RULE,
                   strokeWidth=0.8))
        d.add(String(cx, 18, team, fontName="Helvetica", fontSize=8, textAnchor="middle",
                     fillColor=INK))
    return d


def build_org_chart(path: Path) -> None:
    reporting = [["Role", "Department", "Reports to"],
                 ["Chief Executive Officer (CEO)", "-", "-"]]
    for dept, head, team in DEPARTMENTS:
        reporting.append([head, dept, "Chief Executive Officer (CEO)"])
        reporting.append([team, dept, head])

    story = [
        Paragraph("NovaGear Inc.", TITLE),
        Paragraph("Organization Chart", SUBTITLE),
        Spacer(1, 10),
        Paragraph("Company Profile", H2),
        Paragraph("NovaGear Inc. is a consumer electronics company with about 80 employees. "
                  "The CEO, Alex Morgan, leads four departments: Sales, Operations, Finance, and "
                  "Procurement.", BODY),
        Paragraph("Structure", H2),
        org_tree(),
        Paragraph("Reporting Lines", H2),
        grid_table(reporting, [185, 90, 220]),
        Paragraph("Role Responsibilities", H2),
        grid_table([["Role", "Responsibilities"], *map(list, RESPONSIBILITIES)], [165, 330]),
        Spacer(1, 18),
        Paragraph(FOOTNOTE, FOOT),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=50, rightMargin=50,
                      topMargin=48, bottomMargin=48, title="NovaGear Organization Chart",
                      author="NovaGear Inc.").build(story)


def build_policy(path: Path) -> None:
    story = [
        Paragraph("NovaGear Inc.", TITLE),
        Paragraph("Purchasing Policy", SUBTITLE),
        Spacer(1, 10),
        Paragraph("1. Purpose", H2),
        Paragraph("This policy defines the purchase request, approval, finance validation, and "
                  "procurement handoff process used by NovaGear Inc.", BODY),
        Paragraph("2. Required Information", H2),
        Paragraph("Every purchase request must include: Requester, Department, Requested Item, "
                  "Estimated Cost, and Business Justification. Requests missing required "
                  "information must not proceed to approval.", BODY),
        Paragraph("3. Approval Rules", H2),
        grid_table([["Estimated Cost", "Required Approval"], *map(list, APPROVAL_RULES)], [150, 345]),
        Paragraph("4. Procurement Handoff", H2),
        Paragraph("After all required management and finance approvals are complete, the request "
                  "is handed to the Procurement Department. Procurement is responsible for vendor "
                  "selection, purchase execution, and order follow-up.", BODY),
        Spacer(1, 18),
        Paragraph(FOOTNOTE, FOOT),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=50, rightMargin=50,
                      topMargin=48, bottomMargin=48, title="NovaGear Purchasing Policy",
                      author="NovaGear Inc.").build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    targets = {
        "NovaGear_Organization_Chart.pdf": build_org_chart,
        "NovaGear_Purchasing_Policy.pdf": build_policy,
    }
    for name, build in targets.items():
        out = OUT_DIR / name
        build(out)
        shutil.copyfile(out, WEB_DIR / name)
        print(f"wrote {out.relative_to(ROOT)} and web/public/demo/{name}")


if __name__ == "__main__":
    main()
