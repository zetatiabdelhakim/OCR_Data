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

# Globals to hold loaded assets
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
    """Loads the text corpus and image paths into memory."""
    global CORPUS_WORDS, IMAGE_PATHS

    if os.path.exists(TEXT_FILE_PATH):
        with open(TEXT_FILE_PATH, 'r', encoding='utf-8') as f:
            CORPUS_WORDS = f.read().split()
    else:
        raise FileNotFoundError(f"{TEXT_FILE_PATH} not found.")

    if os.path.exists(IMAGE_FOLDER_PATH):
        valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        IMAGE_PATHS = [
            os.path.join(IMAGE_FOLDER_PATH, f)
            for f in os.listdir(IMAGE_FOLDER_PATH)
            if f.lower().endswith(valid_extensions)
        ]
    else:
        raise FileNotFoundError(f"{IMAGE_FOLDER_PATH} not found.")


def get_real_arabic_text(min_words=30, max_words=300):
    """Pulls a contiguous chunk of real text from the loaded corpus."""
    count = random.randint(min_words, max_words)
    if len(CORPUS_WORDS) > count:
        start_idx = random.randint(0, len(CORPUS_WORDS) - count)
        return " ".join(CORPUS_WORDS[start_idx: start_idx + count])
    elif CORPUS_WORDS:
        return " ".join(CORPUS_WORDS)
    return "نص تجريبي"


def get_image_base64(img_path):
    """Converts a local image to Base64 to bypass Playwright CORS."""
    mime_type, _ = mimetypes.guess_type(img_path)
    if not mime_type:
        mime_type = "image/jpeg"
    with open(img_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:{mime_type};base64,{encoded_string}"


# ==========================================
# 2. DIVERSE LAYOUT COMPONENT GENERATORS
# ==========================================

def gen_paragraph_with_optional_heading(columns=1, include_heading=False):
    text = get_real_arabic_text(100, 300)
    font = random.choice(FONTS)
    color = random.choice(COLORS)
    font_size = random.choice([14, 16, 18])
    col_gap = random.randint(15, 30)
    col_style = f"column-count: {columns}; column-gap: {col_gap}px;" if columns > 1 else ""

    html = '<div style="height: 100%; width: 100%; display: flex; flex-direction: column; box-sizing: border-box; padding-bottom: 20px;">'

    # 2.1 Dynamic Headers Anywhere (H1, H2, H3)
    if include_heading:
        level = random.choice([1, 2, 3])
        h_sizes = {1: 32, 2: 26, 3: 20}
        h_font = random.choice(FONTS)
        h_color = random.choice(COLORS)
        h_text = get_real_arabic_text(3, 8)
        align = random.choice(["right", "center"])

        html += f"""
        <div class="layout-node heading" data-label="h{level}" 
             style="text-align: {align}; font-family: '{h_font}'; color: {h_color}; font-size:{h_sizes[level]}px; font-weight: bold; margin-bottom: 15px; box-sizing: border-box;">
            {h_text}
        </div>
        """

    # Paragraph Body
    html += f"""
    <div class="layout-node paragraph" data-label="paragraph" 
         style="flex-grow: 1; font-family: '{font}'; color: {color}; font-size:{font_size}px; 
                {col_style} text-align: justify; overflow: hidden; line-height: 1.8; box-sizing: border-box;">
        {text}
    </div>
    </div>
    """
    return html


def gen_quote():
    """Generates an analogy, quote, or stylized discourse block."""
    text = get_real_arabic_text(30, 80)
    font = random.choice(FONTS)
    color = random.choice(COLORS)
    bg_color = "#f8fafc"

    return f"""
    <div style="height: 100%; width: 100%; display: flex; align-items: center; justify-content: center; padding-bottom: 20px; box-sizing: border-box;">
        <div class="layout-node quote" data-label="quote" 
             style="width: 90%; max-height: 100%; background-color: {bg_color}; border-right: 6px solid {color}; padding: 20px; font-family: '{font}'; color: {color}; font-size: 18px; font-style: italic; font-weight: bold; overflow: hidden; line-height: 2; box-sizing: border-box; text-align: right;">
            « {text} »
        </div>
    </div>
    """


def gen_poetry():
    """Generates an Arabic poetry block with dual hemistichs (شطرين)."""
    lines = random.randint(3, 6)
    font = random.choice(FONTS)
    color = random.choice(COLORS)
    font_size = random.choice([16, 18, 20])

    html = f'<div class="layout-node poetry" data-label="poetry" style="height: 100%; width: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 15px; font-family: \'{font}\'; color: {color}; font-size: {font_size}px; font-weight: bold; overflow: hidden; box-sizing: border-box; padding-bottom: 20px;">'

    for _ in range(lines):
        part1 = get_real_arabic_text(3, 5)
        part2 = get_real_arabic_text(3, 5)
        html += f"""
        <div class="poetry-line" style="display: flex; width: 85%; justify-content: space-between; gap: 40px; border-bottom: 1px dashed #e2e8f0; padding-bottom: 8px;">
            <span style="flex: 1; text-align: left;">{part1}</span>
            <span style="flex: 1; text-align: right;">{part2}</span>
        </div>
        """
    html += "</div>"
    return html


def gen_figure(caption=None):
    caption = caption or "شكل: " + get_real_arabic_text(2, 6)
    font = random.choice(FONTS)

    if IMAGE_PATHS:
        img_path = random.choice(IMAGE_PATHS)
        img_b64 = get_image_base64(img_path)
        img_html = f'<img src="{img_b64}" style="width: 100%; height: 100%; object-fit: cover; display: block;" />'
    else:
        img_html = f'<span style="font-family: \'{font}\';">[صورة]</span>'

    return f"""
    <div class="layout-node figure-container" data-label="figure" 
         style="height: 100%; width: 100%; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; padding-bottom: 15px;">
        <div style="flex-grow: 1; background:#e2e8f0; border:2px solid #64748b; display:flex; align-items:center; justify-content:center; box-sizing: border-box; overflow: hidden;">
            {img_html}
        </div>
        <div class="layout-node figure-caption" data-label="figure-caption" 
             style="text-align:center; font-family: '{font}'; font-size:14px; margin-top:8px; color:#334155; font-weight: bold; overflow: hidden; box-sizing: border-box;">
            {caption}
        </div>
    </div>
    """


def gen_table(rows=6, cols=3):
    font = random.choice(FONTS)
    color = random.choice(COLORS)

    html = f'<div class="table-wrapper" style="height: 100%; width: 100%; overflow: hidden; box-sizing: border-box; padding-bottom: 15px;">'
    html += f'<table class="layout-node" data-label="table" style="height: 100%; width: 100%; table-layout: fixed; border-collapse: collapse; font-family: \'{font}\'; color: {color}; box-sizing: border-box;">'

    for r in range(rows):
        html += "<tr>"
        for c in range(cols):
            if r == 0:
                html += f'<th class="layout-node" data-label="table-cell" style="border: 2px solid {color}; background-color: #f8fafc; padding: 10px 10px 16px 10px; font-size: 14px; overflow: hidden; box-sizing: border-box;">{get_real_arabic_text(1, 3)}</th>'
            else:
                html += f'<td class="layout-node" data-label="table-cell" style="border: 1px solid {color}; padding: 10px 10px 16px 10px; font-size: 14px; overflow: hidden; box-sizing: border-box;">{get_real_arabic_text(2, 8)}</td>'
        html += "</tr>"
    html += "</table></div>"
    return html


# ==========================================
# 3. PAGE TEMPLATE BUILDER
# ==========================================

def build_html_page(grid_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Almarai:wght@400;700&family=Amiri:wght@400;700&family=Cairo:wght@400;700&family=Changa:wght@400;700&family=Tajawal:wght@400;700&family=Aref+Ruqaa:wght@400;700&display=swap');
            body {{ width: 794px; height: 1123px; margin: 0; padding: 40px; box-sizing: border-box; background-color: white; overflow: hidden; }}
            * {{ box-sizing: border-box; }}
        </style>
    </head>
    <body>
        {grid_html}
    </body>
    </html>
    """


def generate_random_template():
    num_rows = random.randint(2, 4)
    if num_rows == 2:
        row_heights = ["15%", "85%"]
    elif num_rows == 3:
        row_heights = ["15%", "42.5%", "42.5%"]
    else:
        row_heights = ["10%", "30%", "30%", "30%"]

    html = f'<div id="page-grid" style="display: grid; height: 100%; gap: 20px; grid-template-rows: {" ".join(row_heights)};">'

    for r in range(num_rows):
        col_layout = "1fr" if r == 0 else random.choice(["1fr", "1fr 1fr", "1fr 2fr", "2fr 1fr", "1fr 1fr 1fr"])
        cols = col_layout.split()

        html += f'<div style="display: grid; gap: 20px; grid-template-columns: {col_layout}; height: 100%;">'

        for _ in range(len(cols)):
            # Distribute diverse content forms throughout the entire document
            comp_type = \
            random.choices(["para", "quote", "poetry", "table", "figure"], weights=[0.4, 0.15, 0.15, 0.15, 0.15])[0]

            if comp_type == "para":
                inner_cols = random.choice([1, 1, 2]) if len(cols) == 1 else 1
                with_h = random.choice([True, False])
                comp = gen_paragraph_with_optional_heading(columns=inner_cols, include_heading=with_h)
            elif comp_type == "quote":
                comp = gen_quote()
            elif comp_type == "poetry":
                comp = gen_poetry()
            elif comp_type == "table":
                comp = gen_table(rows=random.randint(5, 10), cols=random.randint(2, 4))
            else:
                comp = gen_figure()

            html += f'<div style="height: 100%; overflow: hidden; display: flex; flex-direction: column;">{comp}</div>'

        html += '</div>'
    html += '</div>'
    return build_html_page(html)


# ==========================================
# 4. PLAYWRIGHT EXTRACTION ENGINE
# ==========================================

async def render_and_extract(html_content, output_image_path, output_json_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 794, "height": 1123})
        await page.set_content(html_content, wait_until="networkidle")

        script = """
        () => {
            // STEP 1: FIX TABLES 
            const tableWrappers = document.querySelectorAll('.table-wrapper');
            tableWrappers.forEach(wrapper => {
                const table = wrapper.querySelector('table');
                if (table) {
                    while (wrapper.scrollHeight > wrapper.clientHeight + 1 && table.rows.length > 1) {
                        table.deleteRow(-1); 
                    }
                }
            });

            // STEP 2: AUTO-FIT TEXT (Including Quotes)
            const textNodes = document.querySelectorAll('.paragraph, .heading, .quote, th, td');
            textNodes.forEach(node => {
                while ((node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1) && node.textContent.trim().split(/\\s+/).length > 0) {
                    let text = node.textContent.trim();
                    let words = text.split(/\\s+/);
                    if (words.length <= 1) {
                        node.textContent = ""; 
                        break;
                    }
                    words.pop();
                    node.textContent = words.join(' ');
                }
            });

            // STEP 3: AUTO-FIT POETRY (Remove overflowing lines instead of words to preserve structure)
            const poetryNodes = document.querySelectorAll('.poetry');
            poetryNodes.forEach(node => {
                while (node.scrollHeight > node.clientHeight + 1 && node.children.length > 1) {
                    node.removeChild(node.lastElementChild);
                }
            });

            // STEP 4: EXTRACT EXACT BOUNDING BOXES AND TEXT
            const elements = document.querySelectorAll('.layout-node');
            const data = [];
            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                let extractedText = el.innerText ? el.innerText.trim().replace(/\\s+/g, ' ') : "";
                if (el.getAttribute('data-label') === 'figure') extractedText = "";

                data.push({
                    label: el.getAttribute('data-label'),
                    text: extractedText,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    bottom: rect.bottom,
                    right: rect.right
                });
            });
            return data;
        }
        """
        bounding_boxes = await page.evaluate(script)
        await page.screenshot(path=output_image_path)

        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump({"boxes": bounding_boxes}, f, ensure_ascii=False, indent=4)

        await browser.close()


# ==========================================
# 5. EXECUTION PIPELINE
# ==========================================

async def main():
    load_assets()

    os.makedirs("dataset/images", exist_ok=True)
    os.makedirs("dataset/annotations", exist_ok=True)

    NUM_SAMPLES = 20

    print(f"Generating {NUM_SAMPLES} Advanced A4 templates...")
    for i in tqdm(range(NUM_SAMPLES)):
        html_string = generate_random_template()
        img_path = f"dataset/images/sample_{i:07d}.png"
        json_path = f"dataset/annotations/sample_{i:07d}.json"

        await render_and_extract(html_string, img_path, json_path)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        import nest_asyncio

        nest_asyncio.apply()
        asyncio.run(main())