"""Formal A4 invoice: header, invoice number/date, bill-to block, itemized
table and a totals summary."""

import random
from core import assets, components, hybrid

NAME = "invoice"
BASE_MM = (210, 297)


def _item_table(rows):
    font = assets.get_page_body_font()
    color = random.choice(assets.COLORS)
    headers = ["البيان", "الكمية", "السعر", "المجموع"]
    html = '<div class="layout-node table-wrapper" data-label="table" style="width:100%; overflow:hidden; box-sizing:border-box;">'
    html += f'<table style="width:100%; table-layout:fixed; border-collapse:collapse; font-family:\'{font}\'; color:{color};">'
    html += "<tr>" + "".join(
        f'<th class="layout-node autofit-text" data-label="table-cell" style="border:2px solid {color}; background:#f8fafc; padding:8px; font-size:13px; overflow:hidden;">{h}</th>'
        for h in headers
    ) + "</tr>"
    grand_total = 0.0
    for _ in range(rows):
        qty = random.randint(1, 12)
        price = round(random.uniform(10, 300), 2)
        line_total = qty * price
        grand_total += line_total
        # Use semantic product names for invoice items
        cells = [assets.get_semantic_product(), str(qty), f"{price:,.2f}", f"{line_total:,.2f}"]
        html += "<tr>" + "".join(
            f'<td class="layout-node autofit-text" data-label="table-cell" style="border:1px solid {color}; padding:8px; font-size:12px; overflow:hidden;">{c}</td>'
            for c in cells
        ) + "</tr>"
    html += "</table></div>"
    return html, grand_total


def generate(hybrid_html=""):
    width, height = assets.jittered_size(*BASE_MM)
    font = assets.get_page_body_font()
    title_font = assets.get_page_title_font()

    org_name = assets.get_semantic_org()
    invoice_no = f"INV-{random.randint(1000, 99999)}"
    date_line = f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{random.randint(2023,2026)}"
    bill_to = assets.get_semantic_name()

    table_html, grand_total = _item_table(random.randint(4, 9))

    def block(label, text, size=14, bold=False, align="right", use_title_font=False):
        weight = "bold" if bold else "normal"
        f = title_font if use_title_font else font
        return (f'<div class="layout-node autofit-text" data-label="{label}" '
                f'style="font-family:\'{f}\'; font-size:{size}px; font-weight:{weight}; text-align:{align}; '
                f'margin-bottom:8px; overflow:hidden;">{text}</div>')

    blocks = [
        block("org-name", org_name, size=22, bold=True, align="center", use_title_font=True),
        f'<div style="display:flex; justify-content:space-between; margin-bottom:14px;">'
        f'{block("invoice-number", invoice_no, size=13, align="left")}'
        f'{block("date-line", date_line, size=13, align="right")}</div>',
        block("recipient", "فاتورة إلى: " + bill_to, size=14, bold=True),
        f'<div style="margin:14px 0;">{table_html}</div>',
        f'<div style="display:flex; justify-content:flex-end;">'
        + block("total-line", f"الإجمالي: {grand_total:,.2f}", size=16, bold=True, align="left") + '</div>',
    ]

    if hybrid_html:
        blocks.insert(len(blocks) - 1, hybrid.wrap_hybrid_block(hybrid_html))

    flow = "".join(blocks)
    body = f'<div id="content-flow" style="width:100%; height:100%; padding:44px; box-sizing:border-box;">{flow}</div>'

    return {"width": width, "height": height, "body": body, "auto_height": False}
