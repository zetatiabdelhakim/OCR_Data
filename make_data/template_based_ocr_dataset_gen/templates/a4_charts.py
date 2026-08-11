"""Chart-heavy A4 layout: complex paragraphs (floating images), tables and statistical charts."""

import random
from core import assets, components, hybrid

NAME = "a4_charts"
BASE_MM = (210, 297)


def generate(hybrid_html=""):
    width, height = assets.jittered_size(*BASE_MM)
    num_rows = random.randint(2, 4)
    row_heights = {2: ["15%", "85%"], 3: ["15%", "42.5%", "42.5%"], 4: ["10%", "30%", "30%", "30%"]}[num_rows]

    hybrid_slot_row = random.randint(1, num_rows - 1) if hybrid_html else None

    rows_html = ""
    for r in range(num_rows):
        col_layout = "1fr" if r == 0 else random.choice(["1fr", "1fr 1fr", "1fr 2fr", "2fr 1fr", "1fr 1fr 1fr"])
        cols = col_layout.split()
        rows_html += f'<div style="display: grid; gap: 20px; grid-template-columns: {col_layout}; height: 100%; min-height: 0; overflow: hidden;">'
        placed_hybrid = False
        for _ in range(len(cols)):
            if r == 0:
                comp = components.gen_heading()
            elif r == hybrid_slot_row and not placed_hybrid:
                comp = hybrid.wrap_hybrid_block(hybrid_html)
                placed_hybrid = True
            else:
                comp_type = random.choices(["complex_para", "table", "chart"], weights=[0.5, 0.15, 0.35])[0]
                if comp_type == "complex_para":
                    comp = components.gen_complex_paragraph()
                elif comp_type == "table":
                    comp = components.gen_table(rows=random.randint(4, 7), cols=random.randint(2, 4))
                else:
                    comp = components.gen_chart()
            rows_html += f'<div style="height: 100%; overflow: hidden; display: flex; flex-direction: column; min-height: 0;">{comp}</div>'
        rows_html += "</div>"

    body = (f'<div id="page-grid" style="width:100%; height:100%; padding:40px; box-sizing:border-box; '
            f'display: grid; gap: 20px; grid-template-rows: {" ".join(row_heights)};">{rows_html}</div>')

    body = components.wrap_a4_page(body)

    return {"width": width, "height": height, "body": body, "auto_height": False}
