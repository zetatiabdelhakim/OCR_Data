"""
core/components.py
====================
Reusable HTML building blocks. Every template composes its page out of
these (plus its own bespoke bits). Each function returns a self
contained HTML string following the layout-node / autofit-text /
data-no-text conventions documented in render_engine.py.

Most generators take a `compact` flag - when True they render at a
smaller footprint so they can be used as *hybrid inserts* (a chart
dropped into a receipt, an equation on a book cover, etc.) without
overwhelming the host template.
"""

import random
import base64
from . import assets


# ------------------------------------------------------------------
# Text blocks
# ------------------------------------------------------------------

def gen_heading(text=None, label="heading", font=None, color=None, align=None, font_size=None):
    text = text or assets.get_real_arabic_text(3, 8)
    font = font or random.choice(assets.FONTS)
    color = color or random.choice(assets.COLORS)
    align = align or random.choice(["center", "right"])
    font_size = font_size or random.choice([24, 28, 32, 36])

    return f"""
    <div class="layout-node autofit-text" data-label="{label}"
         style="height: 100%; width: 100%; display: flex; align-items: center; justify-content: {align};
                font-family: '{font}'; color: {color}; font-size:{font_size}px; font-weight: bold;
                overflow: hidden; box-sizing: border-box; padding-bottom: 15px;">
        {text}
    </div>
    """


def gen_paragraph(text=None, columns=1, label="paragraph", font=None, color=None, font_size=None):
    text = text or assets.get_real_arabic_text(100, 300)
    font = font or random.choice(assets.FONTS)
    color = color or random.choice(assets.COLORS)
    font_size = font_size or random.choice([14, 16, 18])

    if columns == 1:
        return f"""
        <div class="layout-node autofit-text" data-label="{label}"
             style="height: 100%; width: 100%; font-family: '{font}'; color: {color}; font-size:{font_size}px;
                    text-align: justify; overflow: hidden; line-height: 1.8; box-sizing: border-box; padding-bottom: 20px;">
            {text}
        </div>
        """

    words = text.split()
    chunk_size = max(1, len(words) // columns)
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    if len(chunks) > columns:
        chunks[columns - 1] += " " + " ".join(chunks[columns:])
        chunks = chunks[:columns]

    col_gap = random.randint(15, 30)
    html = f'<div class="layout-node" data-label="multi-column" style="display: grid; grid-template-columns: repeat({columns}, 1fr); gap: {col_gap}px; height: 100%; width: 100%; box-sizing: border-box; padding-bottom: 20px; min-height: 0; overflow: hidden;">'
    for chunk in chunks:
        html += f"""
        <div class="layout-node autofit-text" data-label="{label}"
             style="height: 100%; width: 100%; font-family: '{font}'; color: {color}; font-size:{font_size}px;
                    text-align: justify; overflow: hidden; line-height: 1.8;">
            {chunk}
        </div>
        """
    html += "</div>"
    return html


def gen_complex_paragraph(compact=False):
    """Paragraph with an inner sub-heading and (70% chance) a floating image - the
    'magazine article' block shared by the charts / image-gallery templates."""
    text = assets.get_real_arabic_text(60, 220 if not compact else 80)
    font = random.choice(assets.FONTS)
    color = random.choice(assets.COLORS)
    font_size = random.choice([14, 16, 18])
    h_level_size = font_size + 6

    img_html = ""
    img_b64 = assets.random_image_b64()
    if img_b64 and random.random() > 0.3:
        float_dir = random.choice(["right", "left"])
        margin_style = "margin: 0 0 10px 15px;" if float_dir == "right" else "margin: 0 15px 10px 0;"
        img_html = f"""
        <div class="layout-node" data-label="figure" style="float: {float_dir}; width: 40%; {margin_style} border: 1px solid #94a3b8; border-radius: 4px; overflow: hidden; background: #e2e8f0; padding: 4px; box-sizing: border-box;">
            <div class="layout-node figure-image" data-label="figure-image" data-no-text="true"><img src="{img_b64}" style="width: 100%; height: auto; display: block;" /></div>
            <div class="layout-node autofit-text" data-label="figure-caption" style="text-align:center; font-size: 12px; margin-top: 4px; color: #334155; font-weight: bold; overflow: hidden;">شكل: {assets.get_real_arabic_text(2, 4)}</div>
        </div>
        """

    return f"""
    <div class="layout-node" data-label="paragraph"
         style="height: 100%; width: 100%; font-family: '{font}'; color: {color}; font-size:{font_size}px;
                text-align: justify; overflow: hidden; line-height: 1.8; box-sizing: border-box; padding-bottom: 15px;
                display: flex; flex-direction: column; min-height: 0;">
        <div class="layout-node autofit-text" data-label="heading" style="margin-top: 0; margin-bottom: 10px; font-size: {h_level_size}px; color: {random.choice(assets.COLORS)}; font-weight: bold; flex-shrink: 0; overflow: hidden;">{assets.get_real_arabic_text(2, 6)}</div>
        {img_html}
        <div class="layout-node autofit-text" data-label="paragraph" style="flex: 1; min-height: 0; overflow: hidden;">{text}</div>
    </div>
    """


def gen_quote():
    text = assets.get_real_arabic_text(10, 30)
    font = random.choice(assets.FONTS)
    color = random.choice(assets.COLORS)
    return f"""
    <div class="layout-node" data-label="quote-block"
         style="height: 100%; width: 100%; display: flex; flex-direction: column; justify-content: center;
                border-right: 4px solid {color}; padding: 10px 20px; box-sizing: border-box; min-height: 0; overflow: hidden;">
        <div class="layout-node autofit-text" data-label="quote"
             style="font-family: '{font}'; font-style: italic; font-size: 20px; color: {color};
                    line-height: 1.8; overflow: hidden; flex: 1; min-height: 0;">
            "{text}"
        </div>
    </div>
    """


def gen_poetry():
    font = random.choice(assets.FONTS)
    color = random.choice(assets.COLORS)
    lines = [assets.get_real_arabic_text(3, 7) for _ in range(random.randint(3, 6))]
    lines_html = "".join(
        f'<div class="layout-node autofit-text" data-label="poetry-line" '
        f'style="font-family: \'{font}\'; font-size: 18px; color: {color}; text-align: center; '
        f'overflow: hidden; padding: 4px 0;">{line}</div>'
        for line in lines
    )
    return f"""
    <div class="layout-node" data-label="poetry-block" style="height: 100%; width: 100%; display: flex;
         flex-direction: column; justify-content: center; box-sizing: border-box; min-height: 0; overflow: hidden;">
        {lines_html}
    </div>
    """


# ------------------------------------------------------------------
# Tables
# ------------------------------------------------------------------

def gen_table(rows=6, cols=3, compact=False):
    font = random.choice(assets.FONTS)
    color = random.choice(assets.COLORS)
    pad = "5px 6px 8px 6px" if compact else "10px 10px 16px 10px"
    fsize = 11 if compact else 14

    html = '<div class="layout-node table-wrapper" data-label="table" style="height: 100%; width: 100%; overflow: hidden; box-sizing: border-box; padding-bottom: 10px;">'
    html += f'<table style="height: 100%; width: 100%; table-layout: fixed; border-collapse: collapse; font-family: \'{font}\'; color: {color}; box-sizing: border-box;">'
    for r in range(rows):
        html += "<tr>"
        for c in range(cols):
            if r == 0:
                html += f'<th class="autofit-text" data-label="table-cell" style="border: 2px solid {color}; background-color: #f8fafc; padding: {pad}; font-size: {fsize}px; overflow: hidden; box-sizing: border-box;">{assets.get_real_arabic_text(1, 3)}</th>'
            else:
                html += f'<td class="autofit-text" data-label="table-cell" style="border: 1px solid {color}; padding: {pad}; font-size: {fsize}px; overflow: hidden; box-sizing: border-box;">{assets.get_real_arabic_text(2, 8)}</td>'
        html += "</tr>"
    html += "</table></div>"
    return html


# ------------------------------------------------------------------
# Figures / images
# ------------------------------------------------------------------

def gen_figure(caption=None, compact=False, label="figure"):
    caption = caption or "شكل: " + assets.get_real_arabic_text(2, 6)
    font = random.choice(assets.FONTS)
    img_b64 = assets.random_image_b64()
    img_html = (f'<img src="{img_b64}" style="width: 100%; height: 100%; object-fit: cover; display: block;" />'
                if img_b64 else f'<span style="font-family: \'{font}\';">[صورة]</span>')
    cap_size = 11 if compact else 14

    return f"""
    <div class="layout-node" data-label="{label}"
         style="height: 100%; width: 100%; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; padding-bottom: 10px;">
        <div class="layout-node figure-image" data-label="figure-image" data-no-text="true"
             style="flex-grow: 1; background:#e2e8f0; border:2px solid #64748b; display:flex; align-items:center; justify-content:center; box-sizing: border-box; overflow: hidden;">
            {img_html}
        </div>
        <div class="layout-node autofit-text" data-label="figure-caption"
             style="text-align:center; font-family: '{font}'; font-size:{cap_size}px; margin-top:6px; color:#334155; font-weight: bold; overflow: hidden; box-sizing: border-box;">
            {caption}
        </div>
    </div>
    """


def gen_image_gallery(n=3, compact=False):
    cells = ""
    for _ in range(n):
        img_b64 = assets.random_image_b64()
        img_html = (f'<img src="{img_b64}" style="width:100%; height:100%; object-fit:cover; display:block;" />'
                    if img_b64 else '<div style="width:100%;height:100%;background:#e2e8f0;"></div>')
        cells += f'<div class="layout-node" data-label="figure-image" data-no-text="true" style="overflow:hidden; border:1px solid #94a3b8;">{img_html}</div>'
    gap = 6 if compact else 12
    return f"""
    <div class="layout-node" data-label="image-gallery"
         style="height: 100%; width: 100%; display: grid; grid-template-columns: repeat({n}, 1fr); gap: {gap}px; box-sizing: border-box; padding-bottom: 10px;">
        {cells}
    </div>
    """


# ------------------------------------------------------------------
# Charts (Chart.js canvases)
# ------------------------------------------------------------------

_CHART_TYPES = [
    "type: 'bar', data: {{labels: [{labels}], datasets: [{{label: 'A', data: {d1}, backgroundColor: 'rgba(54,162,235,0.6)'}}]}}",
    "type: 'bar', data: {{labels: [{labels}], datasets: [{{label: 'A', data: {d1}, backgroundColor:'#36a2eb'}},{{label:'B', data: {d2}, backgroundColor:'#ffce56'}}]}}",
    "type: 'line', data: {{labels: [{labels}], datasets: [{{label: 'Trend', data: {d1}, borderColor: '#4bc0c0', tension: 0.1}}]}}",
    "type: 'line', data: {{labels: [{labels}], datasets: [{{label:'Area', data: {d1}, borderColor:'#9966ff', backgroundColor:'rgba(153,102,255,0.2)', fill:true}}]}}",
    "type: 'pie', data: {{labels: [{labels}], datasets: [{{data: {d1}, backgroundColor: ['#ff6384','#36a2eb','#cc65fe','#ffce56','#4bc0c0']}}]}}",
    "type: 'doughnut', data: {{labels: [{labels}], datasets: [{{data: {d2}, backgroundColor: ['#ff6384','#36a2eb','#cc65fe','#ffce56','#4bc0c0']}}]}}",
    "type: 'radar', data: {{labels: [{labels}], datasets: [{{label:'Metrics', data: {d1}, backgroundColor:'rgba(255,99,132,0.2)', borderColor:'#ff6384'}}]}}",
    "type: 'polarArea', data: {{labels: [{labels}], datasets: [{{data: {d1}, backgroundColor: ['rgba(255,99,132,0.5)','rgba(54,162,235,0.5)','rgba(255,206,86,0.5)','rgba(75,192,192,0.5)','rgba(153,102,255,0.5)']}}]}}",
]


def gen_chart(compact=False):
    chart_id = f"chart_{random.randint(10000, 999999)}"
    labels = ",".join(f"'{assets.get_real_arabic_text(1, 2)}'" for _ in range(5))
    d1 = [random.randint(10, 100) for _ in range(5)]
    d2 = [random.randint(10, 100) for _ in range(5)]
    config = random.choice(_CHART_TYPES).format(labels=labels, d1=d1, d2=d2)
    font = random.choice(assets.FONTS)
    title_size = 11 if compact else 14
    title = "" if compact else f'<div style="text-align:center; font-family:\'{font}\'; font-weight:bold; font-size:{title_size}px; margin-bottom:5px;">شكل إحصائي: {assets.get_real_arabic_text(2, 5)}</div>'

    return f"""
    <div class="layout-node" data-label="chart" style="height: 100%; width: 100%; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; padding-bottom: 10px;">
        {title}
        <div style="flex-grow: 1; position: relative; width: 100%; height: 100%;" data-no-text="true">
            <canvas id="{chart_id}" data-no-text="true"></canvas>
        </div>
        <script>
            new Chart(document.getElementById('{chart_id}'), {{
                {config},
                options: {{ animation: false, maintainAspectRatio: false }}
            }});
        </script>
    </div>
    """


# ------------------------------------------------------------------
# Equations (KaTeX, rendered client-side from base64 LaTeX)
# ------------------------------------------------------------------

_EQ_VARS = ['x', 'y', 'z', 't', 'k', 'n', 'i', 'j', r'\theta', r'\alpha', r'\beta', r'\mu', r'\sigma', r'\lambda']
_EQ_OPS = ['+', '-', r'\times', r'\cdot', '=', r'\approx', r'\leq', r'\geq']
_EQ_FUNCS = [r'\sin', r'\cos', r'\tan', r'\log', r'\ln', r'\exp', r'\max', r'\min']

_EQ_TEMPLATES = [
    r"\int_{{{lb}}}^{{{ub}}} {func}({v}) \, d{v} = {v2}^2 {op} C",
    r"\iint_{{D}} {v}^2 {op} {v2}^2 \, dx \, dy",
    r"\sum_{{{v}=0}}^{{{ub}}} \frac{{{v2}^{v}}}{{{v}!}} = e^{{{v2}}}",
    r"\prod_{{{v}=1}}^{{n}} (1 {op} {v2}_{v}) = 0",
    r"\nabla_{{{v}}} J({v}) = \frac{{1}}{{m}} X^T ( \sigma(X {v}) - Y )",
    r"\mathbb{{E}}[{v}] = \int x f_{v}(x) dx",
    r"\frac{{\partial {v}}}{{\partial {v2}}} = \lim_{{h \to 0}} \frac{{{func}({v2} + h) - {func}({v2})}}{{h}}",
    r"{v}_{{n+1}} = {v}_n - \alpha \nabla f({v}_n)",
    r"P(A|B) = \frac{{P(A \cap B)}}{{P(B)}}",
    r"\vec{{F}} = m\vec{{a}}",
]


def gen_dynamic_equation():
    tpl = random.choice(_EQ_TEMPLATES)
    eq = tpl.format(
        v=random.choice(_EQ_VARS), v2=random.choice(_EQ_VARS),
        lb=random.randint(0, 5), ub=random.choice(['\\infty', 'N', 'M', '100']),
        op=random.choice(_EQ_OPS), func=random.choice(_EQ_FUNCS),
    )
    if random.random() > 0.7:
        eq += r" + \frac{" + random.choice(_EQ_VARS) + r"}{" + random.choice(_EQ_VARS) + r"^2}"
    return eq


def _b64_latex(eq):
    return base64.b64encode(eq.encode('utf-8')).decode('utf-8')


def gen_display_equation(compact=False):
    eq = gen_dynamic_equation()
    fsize = random.choice([13, 15]) if compact else random.choice([16, 18, 20])
    return f"""
    <div class="layout-node katex-display-math" data-label="equation" data-math="{_b64_latex(eq)}"
         style="text-align: center; margin: 10px 0; font-size: {fsize}px; direction: ltr; overflow: hidden; break-inside: avoid;">
    </div>
    """


def gen_theorem_box(compact=False):
    font = random.choice(assets.FONTS)
    box_type = random.choice(["نظرية", "تعريف", "مبرهنة", "ملاحظة", "برهان"])
    bg_color = random.choice(["#f8fafc", "#f0fdf4", "#fffbeb", "#fef2f2"])
    border_color = random.choice(["#94a3b8", "#4ade80", "#fcd34d", "#f87171"])
    eq = gen_dynamic_equation()
    body_words = (10, 30) if compact else (20, 60)

    return f"""
    <div class="layout-node" data-label="theorem-box"
         style="break-inside: avoid; margin-bottom: 14px; background-color: {bg_color};
                border-right: 4px solid {border_color}; padding: 12px; font-family: '{font}'; box-sizing: border-box;">
        <div class="layout-node autofit-text" data-label="theorem-title" style="font-size: 16px; font-weight: bold; overflow: hidden;">{box_type}</div>
        <div class="layout-node autofit-text" data-label="paragraph" style="font-size: 14px; line-height: 1.6; margin: 5px 0; overflow: hidden;">{assets.get_real_arabic_text(*body_words)}</div>
        <div class="layout-node katex-display-math" data-label="equation" data-math="{_b64_latex(eq)}"
             style="text-align: center; direction: ltr; margin-top: 8px; overflow: hidden;"></div>
    </div>
    """


# ------------------------------------------------------------------
# Branding bits - logo & barcode placeholders (no real logo assets available,
# so a "logo" is a stylised text/shape mark, consistent with the rest of
# the synthetic-but-plausible approach used throughout this pipeline)
# ------------------------------------------------------------------

def gen_logo(mark_text=None, compact=False):
    mark_text = mark_text or assets.get_real_arabic_text(1, 1)
    font = random.choice(assets.DISPLAY_FONTS)
    color = random.choice(assets.COLORS)
    shape = random.choice(["circle", "square", "hexagon"])
    size = 46 if compact else 64
    radius = "50%" if shape == "circle" else ("12px" if shape == "square" else "8px")

    return f"""
    <div class="layout-node" data-label="logo"
         style="width:{size}px; height:{size}px; border-radius:{radius}; background:{color};
                display:flex; align-items:center; justify-content:center; box-sizing:border-box;">
        <span class="layout-node autofit-text" data-label="logo-mark"
              style="font-family:'{font}'; color:white; font-size:{int(size*0.45)}px; font-weight:bold; overflow:hidden;">{mark_text}</span>
    </div>
    """


def gen_barcode(compact=False):
    bars = "".join(
        f'<div style="width:{random.choice([2,3,4])}px; height:100%; background:#111; margin-right:1px;"></div>'
        for _ in range(random.randint(30, 45))
    )
    height = 30 if compact else 44
    return f"""
    <div class="layout-node" data-label="barcode" data-no-text="true"
         style="height:{height}px; width:100%; display:flex; flex-direction:row-reverse; align-items:stretch; overflow:hidden; box-sizing:border-box;">
        {bars}
    </div>
    """


# ------------------------------------------------------------------
# Headers and Footers (for A4 pages)
# ------------------------------------------------------------------

def gen_header():
    font = random.choice(assets.FONTS)
    text = assets.get_real_arabic_text(2, 6)
    return f"""
    <div class="layout-node" data-label="header" style="width: 100%; padding: 10px 40px; border-bottom: 2px solid #ccc; box-sizing: border-box; display: flex; justify-content: space-between; align-items: center; font-family: '{font}'; font-size: 14px; font-weight: bold; color: #333;">
        <span class="layout-node autofit-text" data-label="header" style="overflow: hidden; max-width: 80%;">{text}</span>
        <span class="layout-node autofit-text" data-label="header" style="overflow: hidden;">{random.randint(1, 100)}</span>
    </div>
    """

def gen_footer():
    font = random.choice(assets.FONTS)
    return f"""
    <div class="layout-node" data-label="footer" style="width: 100%; padding: 10px 40px; border-top: 1px solid #ccc; box-sizing: border-box; display: flex; justify-content: center; align-items: center; font-family: '{font}'; font-size: 12px; color: #666;">
        <span class="layout-node autofit-text" data-label="footer" style="overflow: hidden;">الصفحة {random.randint(1, 99)}</span>
    </div>
    """

def wrap_a4_page(inner_body_html):
    """Wraps the inner content-flow of an A4 template in a flex column to safely inject headers and footers without breaking the flow."""
    header_html = gen_header() if random.random() < 0.2 else ""
    footer_html = gen_footer() if random.random() < 0.2 else ""
    
    return f"""
    <div style="display:flex; flex-direction:column; width:100%; height:100%; background:white; overflow:hidden; box-sizing:border-box;">
        {header_html}
        <div style="flex:1; position:relative; overflow:hidden; box-sizing:border-box; min-height: 0;">
            {inner_body_html}
        </div>
        {footer_html}
    </div>
    """
