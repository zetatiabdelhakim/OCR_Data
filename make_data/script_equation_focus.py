import os
import json
import random
import asyncio
import base64
import mimetypes
from playwright.async_api import async_playwright
from tqdm import tqdm

# ==========================================
# 1. DATA, FONTS, COLORS & ASSETS
# ==========================================

TEXT_FILE_PATH = "shamela_1M_words.txt"
IMAGE_FOLDER_PATH = "nature_images"

# Global Paths
DATASET_IMAGES_PATH = "dataset/images"
DATASET_ANNOTATIONS_PATH = "dataset/annotations"

CORPUS_WORDS = []
IMAGE_PATHS = []

FONTS = [
    'Amiri', 'Cairo', 'Tajawal', 'Almarai', 'Aref Ruqaa', 'Changa',
    'Noto Naskh Arabic', 'Noto Kufi Arabic', 'IBM Plex Sans Arabic',
    'Alexandria', 'El Messiri', 'Markazi Text', 'Lateef', 'Reem Kufi',
    'Scheherazade New', 'Mada', 'Mirza', 'Harmattan', 'Baloo Bhaijaan 2',
    'Readex Pro', 'Rakkas', 'Katibeh', 'Lalezar', 'Vazirmatn', 'Rubik Arabic', 'Noto Sans Arabic'
]

COLORS = [
    "#000000", "#111111", "#1f1f1f", "#2d2d2d", "#404040", "#555555", "#666666",
    "#1e3a8a", "#1d4ed8", "#2563eb", "#1e40af", "#0f172a", "#14532d", "#166534",
    "#15803d", "#0f766e", "#7f1d1d", "#991b1b", "#b91c1c", "#dc2626", "#4c1d95",
    "#6d28d9", "#78350f", "#92400e", "#854d0e", "#334155", "#475569",
]


def load_assets():
    global CORPUS_WORDS, IMAGE_PATHS
    if os.path.exists(TEXT_FILE_PATH):
        with open(TEXT_FILE_PATH, 'r', encoding='utf-8') as f:
            CORPUS_WORDS = f.read().split()
    else:
        print(f"Warning: {TEXT_FILE_PATH} not found. Using fallback text.")

    if os.path.exists(IMAGE_FOLDER_PATH):
        valid_ext = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        IMAGE_PATHS = [os.path.join(IMAGE_FOLDER_PATH, f) for f in os.listdir(IMAGE_FOLDER_PATH) if
                       f.lower().endswith(valid_ext)]
    else:
        print(f"Warning: {IMAGE_FOLDER_PATH} not found. Figures will use fallback.")


def get_real_arabic_text(min_words=30, max_words=150):
    count = random.randint(min_words, max_words)
    if len(CORPUS_WORDS) > count:
        start_idx = random.randint(0, len(CORPUS_WORDS) - count)
        return " ".join(CORPUS_WORDS[start_idx: start_idx + count])
    return "نص تجريبي للذكاء الاصطناعي ومعالجة اللغات الطبيعية " * (count // 5)


def get_image_base64(img_path):
    mime_type, _ = mimetypes.guess_type(img_path)
    with open(img_path, "rb") as image_file:
        return f"data:{mime_type or 'image/jpeg'};base64,{base64.b64encode(image_file.read()).decode('utf-8')}"


# ==========================================
# 2. DYNAMIC MATH GENERATOR (Base64 Safe)
# ==========================================

def gen_dynamic_equation():
    """Dynamically constructs highly diverse, syntax-safe LaTeX equations."""
    vars = ['x', 'y', 'z', 't', 'k', 'n', 'i', 'j', '\\theta', '\\alpha', '\\beta', '\\mu', '\\sigma', '\\lambda']
    ops = ['+', '-', '\\times', '\\cdot', '=', '\\approx', '\\leq', '\\geq']
    functions = ['\\sin', '\\cos', '\\tan', '\\log', '\\ln', '\\exp', '\\max', '\\min']

    templates = [
        r"\int_{{{lb}}}^{{{ub}}} {func}({v}) \, d{v} = {v2}^2 {op} C",
        r"\iint_{{D}} {v}^2 {op} {v2}^2 \, dx \, dy",
        r"\sum_{{{v}=0}}^{{{ub}}} \frac{{{v2}^{v}}}{{{v}!}} = e^{{{v2}}}",
        r"\prod_{{{v}=1}}^{{n}} (1 {op} {v2}_{v}) = 0",
        r"L({v}) = - \frac{{1}}{{N}} \sum_{{{v}=1}}^N \left[ y_{v} \log(\hat{{y}}_{v}) {op} (1-y_{v}) \log(1-\hat{{y}}_{v}) \right]",
        r"\nabla_{{{v}}} J({v}) = \frac{{1}}{{m}} X^T ( \sigma(X {v}) - Y )",
        r"\mathbb{{E}}[{v}] = \int x f_{v}(x) dx",
        r"{v} = \begin{{bmatrix}} {n1} & {n2} \\ {n3} & {n4} \end{{bmatrix}} \begin{{bmatrix}} {v2} \\ {v3} \end{{bmatrix}}",
        r"\frac{{\partial {v}}}{{\partial {v2}}} = \lim_{{h \to 0}} \frac{{{func}({v2} + h) - {func}({v2})}}{{h}}",
        r"{v}_{{n+1}} = {v}_n - \alpha \nabla f({v}_n)"
    ]

    eq = random.choice(templates).format(
        v=random.choice(vars), v2=random.choice(vars), v3=random.choice(vars),
        lb=random.randint(0, 5), ub=random.choice(['\\infty', 'N', 'M', '100']),
        op=random.choice(ops), func=random.choice(functions),
        n1=random.randint(0, 9), n2=random.randint(0, 9), n3=random.randint(0, 9), n4=random.randint(0, 9)
    )

    if random.random() > 0.7:
        eq += r" + \frac{" + random.choice(vars) + r"}{" + random.choice(vars) + r"^2}"

    return eq


# ==========================================
# 3. HIERARCHICAL COMPONENT GENERATORS
# ==========================================

def gen_paper_title():
    text = get_real_arabic_text(5, 12)
    font = random.choice(FONTS)
    return f"""
    <div class="layout-node heading" data-label="h1_title" 
         style="column-span: all; text-align: center; font-family: '{font}'; 
                font-size: 32px; font-weight: bold; margin-bottom: 25px; 
                border-bottom: 2px solid #333; padding-bottom: 10px;">
        {text}
    </div>
    """


def gen_abstract():
    text = get_real_arabic_text(40, 80)
    font = random.choice(FONTS)
    return f"""
    <div class="layout-node paragraph" data-label="abstract" 
         style="column-span: all; font-family: '{font}'; font-size: 14px; 
                text-align: justify; margin: 0 40px 20px 40px; font-weight: bold; 
                border-top: 1px solid #ccc; border-bottom: 1px solid #ccc; padding: 10px 0;">
        <span style="color: #666;">الملخص: </span> {text}
    </div>
    """


def gen_section():
    level = random.choice(["h2", "h3"])
    size = "22px" if level == "h2" else "18px"
    font = random.choice(FONTS)
    para_text = get_real_arabic_text(50, 150)

    if random.random() < 0.5:
        inline_templates = [
            r"\alpha + \beta = \gamma", r"\int f(x)dx", r"\sum_{i=1}^n x_i",
            r"x^2 + y^2 = r^2", r"P(A|B) = \frac{P(A \cap B)}{P(B)}", r"\vec{F} = m\vec{a}"
        ]
        eq = random.choice(inline_templates)
        eq_b64 = base64.b64encode(eq.encode('utf-8')).decode('utf-8')
        math_html = f'<span class="katex-inline-math" data-math="{eq_b64}"></span>'

        words = para_text.split()
        insert_idx = len(words) // 2
        words.insert(insert_idx, math_html)
        para_text = " ".join(words)

    return f"""
    <div style="margin-bottom: 20px; break-inside: avoid;">
        <div class="layout-node heading" data-label="{level}" 
             style="font-family: '{font}'; font-size: {size}; font-weight: bold; 
                    margin-bottom: 10px; color: {random.choice(COLORS)}; break-after: avoid;">
            {get_real_arabic_text(3, 8)}
        </div>
        <div class="layout-node paragraph" data-label="paragraph" 
             style="font-family: '{font}'; font-size: 14px; text-align: justify; line-height: 1.8;">
            {para_text}
        </div>
    </div>
    """


def gen_theorem_box():
    font = random.choice(FONTS)
    box_type = random.choice(["نظرية", "تعريف", "مبرهنة", "ملاحظة"])
    bg_color = random.choice(["#f8fafc", "#f0fdf4", "#fffbeb", "#fef2f2"])
    border_color = random.choice(["#94a3b8", "#4ade80", "#fcd34d", "#f87171"])

    eq = gen_dynamic_equation()
    eq_b64 = base64.b64encode(eq.encode('utf-8')).decode('utf-8')

    return f"""
    <div class="layout-node paragraph" data-label="theorem_box" 
         style="break-inside: avoid; margin-bottom: 20px; background-color: {bg_color}; 
                border-right: 4px solid {border_color}; padding: 15px; font-family: '{font}';">
        <strong style="font-size: 16px;">{box_type}:</strong>
        <p style="font-size: 14px; line-height: 1.6; margin: 5px 0;">{get_real_arabic_text(20, 60)}</p>
        <div class="layout-node math-block katex-display-math" data-label="equation" data-math="{eq_b64}" 
             style="text-align: center; direction: ltr; margin-top: 10px;">
        </div>
    </div>
    """


def gen_display_equation():
    eq = gen_dynamic_equation()
    eq_b64 = base64.b64encode(eq.encode('utf-8')).decode('utf-8')
    span_style = 'column-span: all;' if random.random() > 0.8 else ''

    return f"""
    <div class="layout-node math-block katex-display-math" data-label="equation" data-math="{eq_b64}"
         style="text-align: center; margin: 15px 0; font-size: {random.choice([14, 16, 18])}px; 
                break-inside: avoid; direction: ltr; {span_style} overflow: hidden;">
    </div>
    """


def gen_figure():
    caption = "شكل: " + get_real_arabic_text(4, 10)
    font = random.choice(FONTS)
    span_style = 'column-span: all;' if random.random() > 0.8 else ''

    img_html = f'<img src="{get_image_base64(random.choice(IMAGE_PATHS))}" style="width: 100%; object-fit: contain; max-height: 250px;" />' if IMAGE_PATHS else f'<div style="padding: 40px; background: #eee;">[صورة علمية]</div>'

    return f"""
    <div style="margin-bottom: 20px; break-inside: avoid; {span_style}">
        <div class="layout-node figure" data-label="figure" style="border: 1px solid #ccc; padding: 5px;">
            {img_html}
        </div>
        <div class="layout-node caption" data-label="figure-caption" 
             style="text-align: center; font-family: '{font}'; font-size: 12px; margin-top: 8px; font-weight: bold;">
            {caption}
        </div>
    </div>
    """


def gen_table():
    rows = random.randint(3, 8)
    cols = random.randint(2, 5)
    font = random.choice(FONTS)
    span_style = 'column-span: all;' if cols > 3 else ''

    html = f'<div style="margin-bottom: 20px; break-inside: avoid; {span_style} overflow: hidden;">'
    html += f'<table class="layout-node table" data-label="table" style="width: 100%; border-collapse: collapse; font-family: \'{font}\'; font-size: 13px;">'
    for r in range(rows):
        html += "<tr>"
        for c in range(cols):
            cell_type = "th" if r == 0 else "td"
            bg = "background: #f1f5f9;" if r == 0 else ""
            html += f'<{cell_type} data-label="table-cell" style="border: 1px solid #000; padding: 8px; {bg} text-align: center;">{get_real_arabic_text(1, 4)}</{cell_type}>'
        html += "</tr>"
    html += "</table></div>"
    return html


# ==========================================
# 4. SCIENTIFIC PAGE TEMPLATE BUILDER
# ==========================================

def generate_scientific_template():
    html = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
        <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Almarai:wght@400;700&family=Amiri:wght@400;700&family=Cairo:wght@400;700&family=Changa:wght@400;700&family=Tajawal:wght@400;700&family=Aref+Ruqaa:wght@400;700&display=swap');
            body {
                width: 794px; height: 1123px; margin: 0; padding: 30px; box-sizing: border-box; background-color: white; overflow: hidden;
            }
        </style>
    </head>
    <body>
    """

    cols = random.choices([1, 2, 3], weights=[0.1, 0.75, 0.15])[0]
    html += f'<div id="content-flow" style="column-count: {cols}; column-gap: 30px; height: 100%; width: 100%;">'

    html += gen_paper_title()
    if random.random() > 0.3:
        html += gen_abstract()

    for _ in range(20):
        comp_type = random.choices(
            ["section", "math", "figure", "table", "theorem"],
            weights=[0.4, 0.2, 0.15, 0.15, 0.1]
        )[0]

        if comp_type == "section":
            html += gen_section()
        elif comp_type == "math":
            html += gen_display_equation()
        elif comp_type == "figure":
            html += gen_figure()
        elif comp_type == "theorem":
            html += gen_theorem_box()
        else:
            html += gen_table()

    html += """
        </div>
    </body>
    </html>
    """
    return html


# ==========================================
# 5. PLAYWRIGHT EXTRACTION ENGINE
# ==========================================

def assign_block_preserving_index(boxes):
    """
    Respects native DOM block order.
    Parents get -1. Children get sequential 1, 2, 3...
    """
    counter = 1
    for box in boxes:
        if box.get('is_parent'):
            box['reading_index'] = -1
        else:
            box['reading_index'] = counter
            counter += 1
        # Clean up temporary flag
        box.pop('is_parent', None)
    return boxes


async def render_and_extract(html_content, output_image_path, output_json_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 794, "height": 1123})

        await page.set_content(html_content, wait_until="networkidle")

        script = """
        () => {
            // STEP 0: Inject layout-node classes to inner text elements so Playwright sees them.
            // This prevents missing text in boxes (like theorems) that mix text and inner layout-nodes.
            document.querySelectorAll('[data-label="theorem_box"] p, [data-label="theorem_box"] strong').forEach(el => {
                el.classList.add('layout-node');
                if(!el.getAttribute('data-label')) el.setAttribute('data-label', 'paragraph');
            });

            // STEP 1: Decode Base64 and Render explicit KaTeX elements
            document.querySelectorAll('.katex-display-math').forEach(el => {
                const rawMath = decodeURIComponent(escape(atob(el.getAttribute('data-math'))));
                katex.render(rawMath, el, {displayMode: true, throwOnError: false});
            });
            document.querySelectorAll('.katex-inline-math').forEach(el => {
                const rawMath = decodeURIComponent(escape(atob(el.getAttribute('data-math'))));
                katex.render(rawMath, el, {displayMode: false, throwOnError: false});
            });

            // STEP 2: CROP OUT OF BOUNDS SAFELY
            const SAFE_RIGHT = 770; 
            const SAFE_BOTTOM = 1100;

            const container = document.getElementById('content-flow');
            if (container) {
                const blocks = Array.from(container.children);
                blocks.forEach(block => {
                    const rect = block.getBoundingClientRect();
                    if (rect.right > SAFE_RIGHT || rect.bottom > SAFE_BOTTOM || rect.left < 25 || rect.top < 25 || rect.width === 0) {
                        block.remove();
                    }
                });
            }

            // STEP 3: NATIVE DOM EXTRACTION (PRESERVES BLOCK-BY-BLOCK FLOW)
            const elements = document.querySelectorAll('.layout-node, td, th');
            const data = [];

            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                const label = el.getAttribute('data-label') || 'table-cell';

                // Intelligently identify parents: if it contains inner layout-nodes or cells, it's a wrapper.
                const children = el.querySelectorAll('.layout-node, td, th');
                const isParent = children.length > 0;

                // Extract text only if it's a leaf node.
                let extractedText = "";
                if (!isParent && label !== 'figure') {
                    extractedText = el.innerText ? el.innerText.trim().replace(/\\s+/g, ' ') : "";
                }

                data.push({
                    label: label,
                    text: extractedText,
                    is_parent: isParent, // Consumed by Python
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                });
            });
            return data;
        }
        """

        bounding_boxes = await page.evaluate(script)

        # Apply block-preserving indexing (-1 for parents, 1..N for children)
        bounding_boxes = assign_block_preserving_index(bounding_boxes)

        await page.screenshot(path=output_image_path)

        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump({"boxes": bounding_boxes}, f, ensure_ascii=False, indent=4)

        await browser.close()


# ==========================================
# 6. EXECUTION PIPELINE
# ==========================================

async def main():
    load_assets()
    os.makedirs(DATASET_IMAGES_PATH, exist_ok=True)
    os.makedirs(DATASET_ANNOTATIONS_PATH, exist_ok=True)

    NUM_SAMPLES = 20

    print(f"Generating {NUM_SAMPLES} Perfected Scientific Paper layouts...")
    for i in tqdm(range(NUM_SAMPLES)):
        html_string = generate_scientific_template()
        img_path = os.path.join(DATASET_IMAGES_PATH, f"sample_{i:07d}.png")
        json_path = os.path.join(DATASET_ANNOTATIONS_PATH, f"sample_{i:07d}.json")

        await render_and_extract(html_string, img_path, json_path)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        import nest_asyncio

        nest_asyncio.apply()
        asyncio.run(main())