"""Generate sample Word + Excel files for the insurance middle-market CRM.

Output:
  examples/sample_prospects.xlsx      — Companies + Contacts sheets + Instructions
  examples/sample_outreach_letter.docx — Mail-merge letter with MERGEFIELDs that
                                          pair with the Excel column headers.

Run: python examples/generate_samples.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

OUT_DIR = Path(__file__).resolve().parent


COMPANIES = [
    # name, domain, industry, revenue_band, employees, hq_city, hq_state, lines, notes
    ("Hartwell Precision Manufacturing", "hartwellprecision.com", "Manufacturing",
     "$50M-$250M", 420, "Akron", "OH",
     "Property; GL; Auto; WC; Umbrella; D&O",
     "Renewal 9/1. Incumbent: Chubb. Recent acquisition expanded payroll 18%."),
    ("Meridian Health Partners", "meridianhealth.com", "Healthcare",
     "$250M-$1B", 1850, "Nashville", "TN",
     "Med Mal; Cyber; D&O; EPLI; Property",
     "Cyber sublimit thin; ransomware industry pressure."),
    ("Coastal Logistics Group", "coastallogistics.com", "Distribution",
     "$50M-$250M", 310, "Jacksonville", "FL",
     "Auto; Cargo; GL; WC; Umbrella",
     "Fleet of 240. Loss ratios trending unfavorably; needs telematics story."),
    ("Brightline Real Estate", "brightlinere.com", "Real Estate",
     "$250M-$1B", 95, "Dallas", "TX",
     "Property; GL; Umbrella; D&O; Crime",
     "Portfolio of 38 multifamily assets across TX/AZ. CAT exposure."),
    ("Vanguard Software Labs", "vanguardsoftware.com", "Technology",
     "$10M-$50M", 140, "Austin", "TX",
     "Cyber; Tech E&O; D&O; EPLI",
     "Series C closed Q4; needs D&O tower expansion."),
    ("Northpoint Construction", "northpointbuilds.com", "Construction",
     "$250M-$1B", 680, "Minneapolis", "MN",
     "Builders Risk; GL; WC; Umbrella; Surety",
     "Public works heavy. Surety capacity is the real conversation."),
    ("Ashbury Wealth Advisors", "ashburywealth.com", "Financial Services",
     "$10M-$50M", 65, "Boston", "MA",
     "E&O; D&O; Cyber; EPLI; Crime",
     "Fiduciary E&O renewal in November. SEC exam underway."),
    ("Stillwater Foods Co.", "stillwaterfoods.com", "Manufacturing",
     "$250M-$1B", 920, "Des Moines", "IA",
     "Property; GL; Product Liability; Auto; WC; Recall",
     "Recall coverage thin given recent FDA letter."),
    ("Lakeshore Hospitality Group", "lakeshorehospitality.com", "Hospitality",
     "$50M-$250M", 1100, "Chicago", "IL",
     "Property; GL; Liquor Liability; Umbrella; WC; EPLI",
     "Liquor liability claims trending up post-pandemic."),
    ("Apex Professional Services", "apexpro.com", "Professional Services",
     "$10M-$50M", 220, "Denver", "CO",
     "Professional Liability; D&O; Cyber; EPLI",
     "Bought through retail agent; ready to consider broker change."),
]


CONTACTS = [
    # company_domain, first, last, title, email, conf, linkedin, source, notes
    ("hartwellprecision.com", "Janet", "Reyes", "VP Risk Management",
     "janet.reyes@hartwellprecision.com", 0.95,
     "https://linkedin.com/in/janet-reyes-risk", "linkedin/ddg",
     "Decision maker on P&C. Prefers email over call."),
    ("hartwellprecision.com", "Mark", "Donovan", "Chief Financial Officer",
     "mark.donovan@hartwellprecision.com", 0.90,
     "https://linkedin.com/in/mark-donovan-cfo", "linkedin/ddg",
     "Wants TCOR view, not just premium."),
    ("hartwellprecision.com", "Susan", "Patel", "Controller",
     "susan.patel@hartwellprecision.com", 0.70, "", "permutation",
     "Loops in on renewal week."),

    ("meridianhealth.com", "David", "Liu", "Chief Risk Officer",
     "david.liu@meridianhealth.com", 0.95,
     "https://linkedin.com/in/david-liu-cro", "linkedin/ddg",
     "Cyber is top priority — board-level concern."),
    ("meridianhealth.com", "Rebecca", "Holt", "General Counsel",
     "rebecca.holt@meridianhealth.com", 0.85,
     "https://linkedin.com/in/rebecca-holt-gc", "linkedin/ddg", ""),
    ("meridianhealth.com", "Tom", "Bergman", "Director of Insurance",
     "tom.bergman@meridianhealth.com", 0.70, "", "permutation", ""),

    ("coastallogistics.com", "Marcus", "Ferreira", "Risk Manager",
     "marcus.ferreira@coastallogistics.com", 0.90,
     "https://linkedin.com/in/marcus-ferreira", "linkedin/ddg",
     "Open to telematics conversation."),
    ("coastallogistics.com", "Linda", "Cho", "CFO",
     "linda.cho@coastallogistics.com", 0.85, "", "permutation", ""),

    ("brightlinere.com", "Carla", "Wymer", "VP Finance",
     "carla.wymer@brightlinere.com", 0.95,
     "https://linkedin.com/in/carla-wymer", "linkedin/ddg",
     "Schedule of values updates each Q. CAT modeling matters."),
    ("brightlinere.com", "Andre", "Beck", "General Counsel",
     "andre.beck@brightlinere.com", 0.80, "", "permutation", ""),

    ("vanguardsoftware.com", "Priya", "Shah", "CFO",
     "priya.shah@vanguardsoftware.com", 0.95,
     "https://linkedin.com/in/priya-shah-cfo", "linkedin/ddg",
     "Series C; needs D&O tower built out."),
    ("vanguardsoftware.com", "Eli", "Whittaker", "General Counsel",
     "eli.whittaker@vanguardsoftware.com", 0.90,
     "https://linkedin.com/in/eli-whittaker", "linkedin/ddg", ""),
    ("vanguardsoftware.com", "Sara", "Mendes", "Head of People",
     "sara.mendes@vanguardsoftware.com", 0.70, "", "permutation",
     "EPLI conversation."),

    ("northpointbuilds.com", "Greg", "Olafson", "Director of Risk Management",
     "greg.olafson@northpointbuilds.com", 0.90,
     "https://linkedin.com/in/greg-olafson", "linkedin/ddg",
     "Surety capacity drives the relationship."),
    ("northpointbuilds.com", "Nicole", "Park", "Treasurer",
     "nicole.park@northpointbuilds.com", 0.80, "", "permutation", ""),

    ("ashburywealth.com", "Henry", "Vogel", "Chief Compliance Officer",
     "henry.vogel@ashburywealth.com", 0.95,
     "https://linkedin.com/in/henry-vogel", "linkedin/ddg",
     "SEC exam active; wants E&O review by 9/30."),
    ("ashburywealth.com", "Maya", "Iverson", "CFO",
     "maya.iverson@ashburywealth.com", 0.85, "", "permutation", ""),

    ("stillwaterfoods.com", "Brandon", "McAlister", "VP Risk Management",
     "brandon.mcalister@stillwaterfoods.com", 0.90,
     "https://linkedin.com/in/brandon-mcalister", "linkedin/ddg",
     "Product recall coverage is the open item."),
    ("stillwaterfoods.com", "Audrey", "Lin", "General Counsel",
     "audrey.lin@stillwaterfoods.com", 0.85, "", "permutation", ""),

    ("lakeshorehospitality.com", "Diego", "Ramos", "Director of Risk",
     "diego.ramos@lakeshorehospitality.com", 0.90,
     "https://linkedin.com/in/diego-ramos", "linkedin/ddg",
     "Liquor liability claims trending up."),
    ("lakeshorehospitality.com", "Karen", "Boyle", "CFO",
     "karen.boyle@lakeshorehospitality.com", 0.85, "", "permutation", ""),

    ("apexpro.com", "Trevor", "Knight", "Managing Partner",
     "trevor.knight@apexpro.com", 0.90,
     "https://linkedin.com/in/trevor-knight", "linkedin/ddg",
     "Open to broker change conversation."),
    ("apexpro.com", "Olivia", "Stein", "Director of Operations",
     "olivia.stein@apexpro.com", 0.75, "", "permutation", ""),
]


# ---------- Excel ----------

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFFFF", bold=True, size=11)
TITLE_FONT = Font(bold=True, size=14, color="1F4E78")
HEADER_ALIGN = Alignment(horizontal="left", vertical="center")


def _autosize(ws, max_width: int = 60):
    for col in ws.columns:
        values = [str(c.value) if c.value is not None else "" for c in col]
        width = min(max(len(v) for v in values) + 2, max_width)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(width, 12)


def build_excel(path: Path) -> Path:
    wb = Workbook()

    # --- Instructions sheet ---
    ws0 = wb.active
    ws0.title = "Instructions"
    ws0["A1"] = "Sample prospect list — Insurance middle-market CRM"
    ws0["A1"].font = TITLE_FONT
    notes = [
        "",
        "This workbook has two data sheets you can edit:",
        "   • Companies — one row per target firm",
        "   • Contacts  — one row per buyer-side individual",
        "",
        "Pairs with: sample_outreach_letter.docx",
        "Open the .docx in Microsoft Word, then Mailings → Select Recipients →",
        "   Use Existing List → pick this .xlsx → Contacts sheet.",
        "Word will fill in the merge fields {{first_name}}, {{company}}, etc.",
        "",
        "Or import this workbook into the CRM:",
        "   python -c \"from insurance_crm.importers import import_xlsx, DB; \\",
        "                import_xlsx(DB(), 'examples/sample_prospects.xlsx')\"",
        "",
        "Column meaning is documented in the header row of each sheet.",
    ]
    for i, line in enumerate(notes, start=2):
        ws0.cell(row=i, column=1, value=line)
    ws0.column_dimensions["A"].width = 90

    # --- Companies sheet ---
    ws1 = wb.create_sheet("Companies")
    company_headers = ["name", "domain", "industry", "revenue_band",
                       "employee_count", "hq_city", "hq_state",
                       "lines_of_coverage", "notes"]
    for col, h in enumerate(company_headers, start=1):
        cell = ws1.cell(row=1, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
    for row_idx, row in enumerate(COMPANIES, start=2):
        for col, val in enumerate(row, start=1):
            ws1.cell(row=row_idx, column=col, value=val)
    _add_table(ws1, "Companies_tbl", len(COMPANIES) + 1, len(company_headers))
    _autosize(ws1)
    ws1.freeze_panes = "A2"

    # --- Contacts sheet ---
    ws2 = wb.create_sheet("Contacts")
    contact_headers = ["company_domain", "first_name", "last_name", "title",
                       "email", "email_confidence", "linkedin_url",
                       "source", "notes"]
    for col, h in enumerate(contact_headers, start=1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
    for row_idx, row in enumerate(CONTACTS, start=2):
        for col, val in enumerate(row, start=1):
            ws2.cell(row=row_idx, column=col, value=val)
    _add_table(ws2, "Contacts_tbl", len(CONTACTS) + 1, len(contact_headers))
    _autosize(ws2)
    ws2.freeze_panes = "A2"

    wb.save(path)
    return path


def _add_table(ws, name: str, rows: int, cols: int):
    last_col = get_column_letter(cols)
    ref = f"A1:{last_col}{rows}"
    tbl = Table(displayName=name, ref=ref)
    tbl.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showFirstColumn=False,
        showLastColumn=False, showRowStripes=True, showColumnStripes=False,
    )
    ws.add_table(tbl)


# ---------- Word ----------

def _add_mergefield(paragraph, field_name: str):
    """Insert a real Word MERGEFIELD so Word's native mail merge can fill it in."""
    run = paragraph.add_run()
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = f' MERGEFIELD {field_name} \\* MERGEFORMAT '
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = f"«{field_name}»"
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    sub_run = paragraph.add_run()
    sub_run._r.append(placeholder)
    run2 = paragraph.add_run()
    run2._r.append(fldChar3)


def build_docx(path: Path) -> Path:
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # Letterhead
    head = doc.add_paragraph()
    head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = head.add_run("Your Brokerage, LLC\n")
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)
    head.add_run("123 Insurance Way · Suite 400\n")
    head.add_run("New York, NY 10001\n")
    head.add_run("you@brokerage.com · (212) 555-0100")

    doc.add_paragraph("")

    # Date
    date_p = doc.add_paragraph()
    date_p.add_run("Date: ")
    _add_mergefield(date_p, "merge_date")

    doc.add_paragraph("")

    # Address block — uses merge fields
    addr = doc.add_paragraph()
    _add_mergefield(addr, "first_name"); addr.add_run(" ")
    _add_mergefield(addr, "last_name")
    addr.add_run("\n")
    _add_mergefield(addr, "title"); addr.add_run("\n")
    _add_mergefield(addr, "company"); addr.add_run("\n")

    # Salutation
    salute = doc.add_paragraph()
    salute.add_run("Dear ")
    _add_mergefield(salute, "first_name")
    salute.add_run(",")

    # Body
    body1 = doc.add_paragraph()
    body1.add_run(
        "I work with middle-market companies on their property, casualty, and "
        "executive-risk placements. Several of our clients in similar revenue "
        "bands to "
    )
    _add_mergefield(body1, "company")
    body1.add_run(
        " have recently completed a renewal benchmark and uncovered 10–20% in "
        "structural savings without ceding coverage breadth — typically by "
        "re-marketing primary GL and rebuilding the umbrella tower."
    )

    body2 = doc.add_paragraph(
        "I'm not suggesting a switch. I'm offering a 20-minute benchmark "
        "ahead of your next renewal, with a one-page TCOR comparison you can "
        "share internally. No obligation, no marketing call."
    )

    body3 = doc.add_paragraph()
    body3.add_run("If a brief conversation would be useful, ")
    body3.add_run("I'd welcome the chance to put one together for ").italic = False
    _add_mergefield(body3, "company")
    body3.add_run(".")

    # Sign-off
    doc.add_paragraph("")
    doc.add_paragraph("Sincerely,")
    doc.add_paragraph("")
    sig = doc.add_paragraph()
    sig.add_run("Your Name").bold = True
    doc.add_paragraph("Producer — Commercial Lines")
    doc.add_paragraph("Your Brokerage, LLC")

    # Footer note for the user
    doc.add_paragraph("")
    footer = doc.add_paragraph()
    fr = footer.add_run(
        "── Mail merge instructions ────────────────────────────────────────\n"
        "1. In Word: Mailings → Select Recipients → Use an Existing List\n"
        "2. Pick sample_prospects.xlsx, then the Contacts sheet\n"
        "3. The merge fields above (first_name, last_name, title, company, "
        "merge_date) will resolve automatically\n"
        "4. Mailings → Finish & Merge → Send Email Messages\n"
        "   (Or: Print → save individual letters as PDFs)\n"
        "\n"
        "Same field names work in the Python CRM's templates with Jinja2 "
        "syntax: {{ first_name }}, {{ company }}, etc."
    )
    fr.font.size = Pt(9)
    fr.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    # Page margins
    for section in doc.sections:
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)

    doc.save(path)
    return path


def main():
    xlsx_path = OUT_DIR / "sample_prospects.xlsx"
    docx_path = OUT_DIR / "sample_outreach_letter.docx"
    build_excel(xlsx_path)
    build_docx(docx_path)
    print(f"Wrote {xlsx_path}")
    print(f"Wrote {docx_path}")


if __name__ == "__main__":
    main()
