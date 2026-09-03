"""Builds synthetic fixtures for the evaluation bake-off:
- eval/fixtures/sample.pdf: intro text + a data table + a chart image (bar chart) whose
  values are NOT printed anywhere as text, so answering questions about it requires the
  vision-captioning step, not just PDF text extraction.
- eval/fixtures/sample.xlsx: 2 sheets (Sales, Inventory).
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

REGION_REVENUE = [
    ["Region", "Q1", "Q2", "Q3", "Q4"],
    ["North", "120000", "135000", "150000", "165000"],
    ["South", "98000", "102000", "110000", "115000"],
    ["East", "87000", "91000", "95000", "99000"],
    ["West", "76000", "80000", "85000", "88000"],
]

MONTHLY_VISITORS = {"Jan": 1200, "Feb": 1350, "Mar": 1500, "Apr": 1700, "May": 2200, "Jun": 1900}

SALES_ROWS = [
    ("Widget A", 500, 25000),
    ("Widget B", 300, 18000),
    ("Widget C", 700, 42000),
    ("Widget D", 200, 9000),
]

INVENTORY_ROWS = [
    ("Widget A", "Warehouse-1", 120),
    ("Widget B", "Warehouse-2", 45),
    ("Widget C", "Warehouse-1", 300),
    ("Widget D", "Warehouse-3", 15),
]


def _make_chart_image(path: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(list(MONTHLY_VISITORS.keys()), list(MONTHLY_VISITORS.values()), color="#8b5cf6")
    ax.set_title("Monthly Website Visitors (Jan-Jun 2024)")
    ax.set_ylabel("Visitors")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def generate_pdf() -> str:
    chart_path = os.path.join(FIXTURES_DIR, "_chart.png")
    _make_chart_image(chart_path)

    pdf_path = os.path.join(FIXTURES_DIR, "sample.pdf")
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    story = [
        Paragraph("Acme Corp - Annual Regional Performance Report FY2024", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "This report summarizes regional revenue, quarterly sales figures, and website "
            "traffic trends for the fiscal year. The North region had the highest customer "
            "satisfaction score of 92%.",
            styles["BodyText"],
        ),
        Spacer(1, 24),
        Paragraph("Quarterly Revenue by Region", styles["Heading2"]),
        Table(
            REGION_REVENUE,
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3d1d8c")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ]
            ),
        ),
        Spacer(1, 24),
        Paragraph("Website Traffic Trend", styles["Heading2"]),
        Image(chart_path, width=5 * inch, height=2.9 * inch),
    ]
    doc.build(story)
    os.remove(chart_path)
    return pdf_path


def generate_excel() -> str:
    xlsx_path = os.path.join(FIXTURES_DIR, "sample.xlsx")
    wb = openpyxl.Workbook()

    sales_ws = wb.active
    sales_ws.title = "Sales"
    sales_ws.append(["Product", "UnitsSold", "Revenue"])
    for row in SALES_ROWS:
        sales_ws.append(row)

    inventory_ws = wb.create_sheet("Inventory")
    inventory_ws.append(["Product", "WarehouseLocation", "StockCount"])
    for row in INVENTORY_ROWS:
        inventory_ws.append(row)

    wb.save(xlsx_path)
    return xlsx_path


if __name__ == "__main__":
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    pdf_path = generate_pdf()
    xlsx_path = generate_excel()
    print(f"Generated {pdf_path}")
    print(f"Generated {xlsx_path}")
