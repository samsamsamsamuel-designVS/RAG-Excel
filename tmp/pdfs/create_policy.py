from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from pathlib import Path

out = Path('output/pdf/employee_promotion_test_policy.pdf')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleCustom', fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=colors.HexColor('#17334D'), spaceAfter=12))
styles.add(ParagraphStyle(name='SubtitleCustom', fontName='Helvetica', fontSize=10, leading=14, textColor=colors.HexColor('#526476'), spaceAfter=16))
styles.add(ParagraphStyle(name='BodyCustom', fontName='Helvetica', fontSize=10, leading=14, spaceAfter=9))
styles.add(ParagraphStyle(name='HeadingCustom', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=colors.HexColor('#17334D'), spaceBefore=9, spaceAfter=7))
styles.add(ParagraphStyle(name='CellCustom', fontName='Helvetica', fontSize=9, leading=12))
P = lambda text: Paragraph(text, styles['BodyCustom'])
H = lambda text: Paragraph(text, styles['HeadingCustom'])
story = []
def table(rows, widths):
    cells = [[Paragraph(str(v), styles['CellCustom']) for v in row] for row in rows]
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7EFF5')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.8,colors.HexColor('#AFC2D2')),('LINEBELOW',(0,1),(-1,-1),.35,colors.HexColor('#DFE6EC'))]))
    return t

story += [Paragraph('Employee Promotion<br/>Shortlisting Policy', styles['TitleCustom']),
          Paragraph('TEST FIXTURE ONLY | Policy TEST-HR-001 | Version 1.0<br/>Effective: 8 November 2026 | Review cycle: FY2026', styles['SubtitleCustom']),
          P('This fictional policy is designed to test spreadsheet and PDF retrieval in an application. It is not an adopted employment policy. A shortlist result is an invitation for human review, not approval of a promotion.'),
          H('1. Scope and required evidence'),
          P('Apply this policy to the <b>Performance Grades</b> worksheet. Use <b>Employee ID</b> as the employee identifier, <b>Full Name</b> as the display name, and <b>FY2025 Grade</b> and <b>FY2026 Grade</b> as the two consecutive review ratings. FY2024 Grade is historical context only and does not determine the FY2026 shortlist.'),
          H('2. Promotion shortlisting rule'),
          P('<b>R1 - Shortlisted:</b> An employee with a valid record is shortlisted when both FY2025 Grade and FY2026 Grade are <b>B or above</b>. The grade order is A (highest), B, C, D, E (lowest). Therefore, two consecutive Grade B ratings qualify. A/A, A/B, and B/A also qualify.'),
          P('<b>R2 - Not shortlisted:</b> If both required grades are valid and either is C, D, or E, the employee is not shortlisted for this cycle. An earlier qualifying pair in FY2024 and FY2025 does not override a lower FY2026 rating.'),
          P('<b>R3 - Manual review required:</b> If either required grade is missing or invalid, or Employee ID is missing or duplicated, classify the record as Manual review required. R3 takes precedence over R1 and R2. Do not treat missing grades as low performance.'),
          H('3. Grade normalization and exclusions'),
          P('Trim leading and trailing whitespace and convert grade text to uppercase before comparison. Only exact values A, B, C, D, and E are valid. Blank values, N/A, numbers, B+, and B- require manual review; do not infer their meaning. Employee IDs must be nonblank after trimming and unique within the worksheet.'),
          P('This test policy has no tenure, salary, job-grade, headcount, or manager-approval threshold for shortlisting. Do not add criteria from Age, Gender, HR Remarks, or other unrelated fields. If other policy documents conflict with these rules, request clarification before producing a final classification.')]

story += [PageBreak(), Paragraph('Evaluation & Test Cases', styles['TitleCustom']),
          Paragraph('TEST-HR-001 | Expected behavior for the FY2026 review cycle', styles['SubtitleCustom']),
          H('4. Evaluation procedure and output'),
          P('Evaluate every uploaded employee record, not only preview rows. First check R3 data quality, then apply R1 or R2. If a required column is absent, request the correct file or an explicit column mapping; do not substitute a numeric Performance Rating field from another file.'),
          P('Return Employee ID, Full Name, FY2025 Grade, FY2026 Grade, Promotion Status, and Reason. Valid status labels are <b>Shortlisted</b>, <b>Not shortlisted</b>, and <b>Manual review required</b>. Include the applied rule ID in Reason and cite this policy with the relevant PDF page. When asked only for shortlisted employees, filter to Shortlisted and state whether any records need manual review.'),
          H('5. Acceptance examples'),
          P('Unless noted otherwise, each example has a unique, nonblank Employee ID. These examples are synthetic and are not employee records.'),
          table([['FY2025', 'FY2026', 'Expected status', 'Rule / explanation'],
                 ['B', 'B', 'Shortlisted', 'R1: two consecutive Grade B ratings'],
                 ['A', 'B', 'Shortlisted', 'R1: both ratings are B or above'],
                 ['B', 'A', 'Shortlisted', 'R1: both ratings are B or above'],
                 ['A', 'A', 'Shortlisted', 'R1: both ratings exceed B'],
                 ['B', 'C', 'Not shortlisted', 'R2: latest rating is below B'],
                 ['C', 'B', 'Not shortlisted', 'R2: prior rating is below B'],
                 ['b', ' B ', 'Shortlisted', 'R1: normalize case and whitespace'],
                 ['B', '(blank)', 'Manual review required', 'R3: missing latest rating'],
                 ['B+', 'A', 'Manual review required', 'R3: B+ is not a valid grade'],
                 ['B', 'B', 'Manual review required', 'R3 if Employee ID is missing or duplicated']],
                [55,55,140,249]),
          H('6. Suggested application questions'),
          P('1. Using the promotion policy, list all employees shortlisted for FY2026 and explain the rule applied.<br/>2. Classify every employee, including records requiring manual review.<br/>3. Count shortlisted employees by Department.<br/>4. Why does an employee with FY2024 B, FY2025 B, and FY2026 C not qualify?<br/>5. Show employees whose records cannot be evaluated because of missing or invalid grades.'),
          P('<b>Expected answer to question 4:</b> Not shortlisted under R2. Only FY2025 and FY2026 determine the FY2026 shortlist; FY2026 C is below B.')]

def footer(c, doc):
    c.setStrokeColor(colors.HexColor('#DFE6EC')); c.line(48,42,A4[0]-48,42)
    c.setFont('Helvetica',8); c.setFillColor(colors.HexColor('#526476'))
    c.drawString(48,29,'TEST-HR-001  |  Fictional policy for application testing')
    c.drawRightString(A4[0]-48,29,f'Page {doc.page}')

doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=44, bottomMargin=56,
                        title='Employee Promotion Shortlisting Policy - Test Fixture', author='Application Test Documents')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(out.resolve())
