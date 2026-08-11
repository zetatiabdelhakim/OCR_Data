"""Academic-paper-style A4 layout: title, abstract, sections with inline math,
theorem boxes, display equations, figures and tables in a CSS multi-column flow."""

import random
from core import assets, components, hybrid

NAME = "a4_paper"
BASE_MM = (210, 297)


def _gen_title():
    text = assets.get_real_arabic_text(5, 12)
    font = random.choice(assets.FONTS)
    return (f'<div class="layout-node autofit-text" data-label="paper-title" '
            f'style="column-span: all; text-align: center; font-family: \'{font}\'; '
            f'font-size: 30px; font-weight: bold; margin-bottom: 20px; '
            f'border-bottom: 2px solid #333; padding-bottom: 10px; overflow: hidden;">{text}</div>')


def _gen_abstract():
    text = assets.get_real_arabic_text(40, 80)
    font = random.choice(assets.FONTS)
    return (f'<div style="break-inside: avoid; max-height: 100%; display: flex; flex-direction: column;">'
            f'<div class="layout-node autofit-text" data-label="abstract" '
            f'style="column-span: all; font-family: \'{font}\'; font-size: 14px; '
            f'text-align: justify; margin: 0 20px 18px 20px; font-weight: bold; '
            f'border-top: 1px solid #ccc; border-bottom: 1px solid #ccc; padding: 10px 0; '
            f'flex: 1; min-height: 0; overflow: hidden;">'
            f'<span style="color:#666;">الملخص: </span>{text}</div></div>')


def _gen_section():
    level_size = random.choice([20, 17])
    font = random.choice(assets.FONTS)
    para_text = assets.get_real_arabic_text(50, 150)
    if random.random() < 0.5:
        words = para_text.split()
        para_text = " ".join(words)
    return f"""
    <div style="margin-bottom: 16px; break-inside: avoid; max-height: 100%; display: flex; flex-direction: column;">
        <div class="layout-node autofit-text" data-label="section-heading"
             style="font-family: '{font}'; font-size: {level_size}px; font-weight: bold; margin-bottom: 8px; color: {random.choice(assets.COLORS)}; flex-shrink: 0; overflow: hidden;">{assets.get_real_arabic_text(3, 8)}</div>
        <div class="layout-node autofit-text" data-label="paragraph"
             style="font-family: '{font}'; font-size: 14px; text-align: justify; line-height: 1.8; flex: 1; min-height: 0; overflow: hidden;">{para_text}</div>
    </div>
    """


def generate(hybrid_html=""):
    width, height = assets.jittered_size(*BASE_MM)
    cols = random.choices([1, 2, 3], weights=[0.1, 0.75, 0.15])[0]

    header_blocks = [_gen_title()]
    if random.random() > 0.3:
        header_blocks.append(_gen_abstract())

    flow_blocks = []
    for _ in range(16):
        comp_type = random.choices(
            ["section", "math", "figure", "table", "theorem"], weights=[0.4, 0.2, 0.15, 0.15, 0.1]
        )[0]
        if comp_type == "section":
            flow_blocks.append(_gen_section())
        elif comp_type == "math":
            flow_blocks.append(components.gen_display_equation())
        elif comp_type == "figure":
            flow_blocks.append(f'<div style="margin-bottom:16px; break-inside: avoid; flex-shrink: 0;">{components.gen_figure()}</div>')
        elif comp_type == "theorem":
            flow_blocks.append(components.gen_theorem_box())
        else:
            flow_blocks.append(f'<div style="margin-bottom:16px; break-inside: avoid; flex-shrink: 0;">{components.gen_table(rows=random.randint(3, 6), cols=random.randint(2, 4))}</div>')

    if hybrid_html:
        insert_at = random.randint(2, len(flow_blocks))
        flow_blocks.insert(insert_at, hybrid.wrap_hybrid_block(hybrid_html))

    headers_html = "".join(header_blocks)
    
    # Distribute blocks evenly into columns to simulate flow
    col_htmls = ["" for _ in range(cols)]
    for i, block in enumerate(flow_blocks):
        col_htmls[i % cols] += block
        
    grid_content = "".join(
        f'<div style="display:flex; flex-direction:column; overflow:hidden; height:100%;">{col_html}</div>' 
        for col_html in col_htmls
    )

    body = (f'<div style="width:100%; height:100%; padding:30px; box-sizing:border-box; display:flex; flex-direction:column;">'
            f'{headers_html}'
            f'<div id="content-flow" style="flex:1; display:grid; grid-template-columns: repeat({cols}, 1fr); gap: 26px; min-height: 0; overflow: hidden;">{grid_content}</div>'
            f'</div>')

    body = components.wrap_a4_page(body)

    return {"width": width, "height": height, "body": body, "auto_height": False}
