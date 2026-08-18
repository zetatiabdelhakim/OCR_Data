"""Thermal-style receipt: narrow fixed width, content-driven (auto) height.
Item lines use semantic product names for realistic document content."""

import random
from core import assets, components, hybrid

NAME = "receipt"
WIDTH_MM_OPTIONS = [58, 80]  # standard thermal roll widths


def _line(label, text, bold=False, size=12, align="right", font=None):
    weight = "bold" if bold else "normal"
    f = font or assets.get_page_body_font()
    return (f'<div class="layout-node autofit-text" data-label="{label}" '
            f'style="font-family:\'{f}\'; font-size:{size}px; font-weight:{weight}; '
            f'text-align:{align}; overflow:hidden; padding:2px 0;">{text}</div>')


def generate(hybrid_html=""):
    width_mm = random.choice(WIDTH_MM_OPTIONS)
    width = assets.jitter(assets.mm_to_px(width_mm), pct=0.08)

    store_name = assets.get_semantic_org()
    date_line = f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{random.randint(2023,2026)} - {random.randint(8,22):02d}:{random.randint(0,59):02d}"

    n_items = random.randint(5, 16)
    total = 0.0
    item_lines = ""
    for _ in range(n_items):
        item_text = assets.get_semantic_product()
        price = assets.random_fake_price(5, 200)
        total += float(price.replace(",", ""))
        item_lines += (
            '<div style="display:flex; justify-content:space-between; gap:6px;">'
            + _line("item-line", item_text, size=11, align="right")
            + _line("price", price, size=11, align="left")
            + '</div>'
        )

    total_line = (
        '<div style="display:flex; justify-content:space-between; border-top:1px dashed #000; margin-top:6px; padding-top:6px;">'
        + _line("total-label", "المجموع", bold=True, size=13, align="right")
        + _line("total-line", f"{total:,.2f}", bold=True, size=13, align="left")
        + '</div>'
    )

    hybrid_block = hybrid.wrap_hybrid_block(hybrid_html, compact_margin=True) if hybrid_html else ""

    body = f"""
    <div id="content-flow" style="width:100%; box-sizing:border-box; padding:14px 10px; background:white;">
        {_line("store-name", store_name, bold=True, size=15, align="center")}
        {_line("date-line", date_line, size=10, align="center")}
        <div style="border-top:1px dashed #000; margin:6px 0;"></div>
        {item_lines}
        {total_line}
        {hybrid_block}
        <div style="margin-top:10px;">{components.gen_barcode(compact=True)}</div>
        {_line("footer-note", "شكرا لزيارتكم", size=10, align="center")}
    </div>
    """

    return {"width": width, "height": 400, "body": body, "auto_height": True}
