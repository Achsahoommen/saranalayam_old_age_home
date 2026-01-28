import os
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

RECEIPT_FOLDER = "receipts"

if not os.path.exists(RECEIPT_FOLDER):
    os.makedirs(RECEIPT_FOLDER)


def generate_receipt(donor):
    """
    donor should contain:
    id, first_name, last_name, email, amount,
    payment_id, date
    """

    receipt_no = f"SAR-{datetime.now().year}-{donor['id']:04d}"
    file_name = f"{receipt_no}.pdf"
    file_path = os.path.join(RECEIPT_FOLDER, file_name)

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph("<b>Saranalayam Old Age Home</b>", styles["Heading1"]))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("<b>Donation Receipt (GST Format)</b>", styles["Heading2"]))
    elements.append(Spacer(1, 20))

    # Organization Info
    org_data = [
        ["Registered Trust:", "Saranalayam Old Age Home"],
        ["Address:", "Chengannur, Kerala, India"],
        ["GSTIN:", "32ABCDE1234F1Z5"],
        ["PAN:", "ABCDE1234F"],
    ]

    org_table = Table(org_data, colWidths=[180, 320])
    org_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(org_table)
    elements.append(Spacer(1, 20))

    # Donor Info
    donor_data = [
        ["Receipt No:", receipt_no],
        ["Date:", donor["date"]],
        ["Donor Name:", f"{donor['first_name']} {donor['last_name']}"],
        ["Email:", donor["email"]],
        ["Payment ID:", donor["payment_id"]],
    ]

    donor_table = Table(donor_data, colWidths=[180, 320])
    donor_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(donor_table)
    elements.append(Spacer(1, 20))

    # Donation Details
    donation_table_data = [
        ["Description", "Amount (INR)"],
        ["Charitable Donation Contribution", f"₹ {donor['amount']:,.2f}"],
    ]

    donation_table = Table(donation_table_data, colWidths=[350, 150])
    donation_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(donation_table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph(
        "Eligible for tax exemption under Section 80G (if applicable).",
        styles["Normal"]
    ))

    elements.append(Spacer(1, 10))

    elements.append(Paragraph(
        "This is a computer-generated receipt and does not require signature.",
        styles["Normal"]
    ))

    doc.build(elements)

    return file_path, receipt_no
