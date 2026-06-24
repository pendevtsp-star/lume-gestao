from io import BytesIO

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def as_text(value):
    if value is None:
        return ""
    return str(value)


def xlsx_response(filename, sheets):
    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    header_fill = PatternFill("solid", fgColor="EDE6D8")
    header_font = Font(bold=True, color="202624")

    for title, headers, rows in sheets:
        worksheet = workbook.create_sheet(title[:31])
        worksheet.append(headers)
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font

        for row in rows:
            worksheet.append([as_text(value) for value in row])

        for column_cells in worksheet.columns:
            max_length = max(len(as_text(cell.value)) for cell in column_cells)
            column_letter = get_column_letter(column_cells[0].column)
            worksheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 48)

    buffer = BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def pdf_response(filename, title, sections=None, tables=None, landscape_page=False):
    buffer = BytesIO()
    page_size = landscape(A4) if landscape_page else A4
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 0.35 * cm)]

    for heading, lines in sections or []:
        story.append(Paragraph(heading, styles["Heading2"]))
        for line in lines:
            story.append(Paragraph(as_text(line), styles["BodyText"]))
        story.append(Spacer(1, 0.25 * cm))

    for heading, headers, rows in tables or []:
        story.append(Paragraph(heading, styles["Heading2"]))
        table_data = [[Paragraph(as_text(value), styles["BodyText"]) for value in headers]]
        for row in rows:
            table_data.append([Paragraph(as_text(value), styles["BodyText"]) for value in row])

        if len(headers) > 4:
            col_width = (page_size[0] - 2.8 * cm) / len(headers)
            col_widths = [col_width] * len(headers)
        else:
            col_widths = None
        table = Table(table_data, repeatRows=1, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDE6D8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#202624")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD4BF")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBF7EE")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 0.35 * cm))

    document.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
