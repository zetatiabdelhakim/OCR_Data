import os
import json
import random
import asyncio
import base64
import mimetypes
from playwright.async_api import async_playwright
from tqdm import tqdm

# ==========================================
# 1. DATA, FONTS, COLORS, ASSETS & PATHS
# ==========================================

TEXT_FILE_PATH = "shamela_1M_words.txt"
IMAGE_FOLDER_PATH = "nature_images"

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
        print(f"Loading text from {TEXT_FILE_PATH}...")
        with open(TEXT_FILE_PATH, 'r', encoding='utf-8') as f:
            CORPUS_WORDS = f.read().split()
    else:
        raise FileNotFoundError(f"{TEXT_FILE_PATH} not found.")

    if os.path.exists(IMAGE_FOLDER_PATH):
        print(f"Scanning images in {IMAGE_FOLDER_PATH}...")
        valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        IMAGE_PATHS = [
            os.path.join(IMAGE_FOLDER_PATH, f) for f in os.listdir(IMAGE_FOLDER_PATH)
            if f.lower().endswith(valid_extensions)
        ]
    else:
        raise FileNotFoundError(f"{IMAGE_FOLDER_PATH} not found.")


def get_real_arabic_text(min_words=30, max_words=300):
    count = random.randint(min_words, max_words)
    if len(CORPUS_WORDS) > count:
        start_idx = random.randint(0, len(CORPUS_WORDS) - count)
        return " ".join(CORPUS_WORDS[start_idx: start_idx + count])
    elif CORPUS_WORDS:
        return " ".join(CORPUS_WORDS)
    return "نص تجريبي"


def get_image_base64(img_path):
    mime_type, _ = mimetypes.guess_type(img_path)
    if not mime_type: mime_type = "image/jpeg"
    with open(img_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:{mime_type};base64,{encoded_string}"


# ==========================================
# 2. HIERARCHICAL LAYOUT GENERATORS
# ==========================================

def gen_heading(text=None):
    text = text or get_real_arabic_text(3, 8)
    font = random.choice(FONTS)
    color = random.choice(COLORS)
    align = random.choice(["center", "right"])
    font_size = random.choice([24, 28, 32, 36])

    return f"""
    <div class="layout-node heading" data-label="heading" 
         style="height: 100%; width: 100%; display: flex; align-items: center; justify-content: {align}; 
                font-family: '{font}'; color: {color}; font-size:{font_size}px; font-weight: bold; overflow: hidden; box-sizing: border-box; padding-bottom: 15px;">
        {text}
    </div>
    """


def gen_paragraph(text=None, columns=1):
    text = text or get_real_arabic_text(100, 300)
    font = random.choice(FONTS)
    color = random.choice(COLORS)
    font_size = random.choice([14, 16, 18])

    # If 1 column, return standard paragraph
    if columns == 1:
        return f"""
        <div class="layout-node paragraph" data-label="paragraph" 
             style="height: 100%; width: 100%; font-family: '{font}'; color: {color}; font-size:{font_size}px; 
                    text-align: justify; overflow: hidden; line-height: 1.8; box-sizing: border-box; padding-bottom: 20px;">
            {text}
        </div>
        """

    # If Multi-column: physically split the text and put it in separate layout-node containers
    words = text.split()
    chunk_size = len(words) // columns
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    if len(chunks) > columns:
        chunks[columns - 1] += " " + " ".join(chunks[columns:])
        chunks = chunks[:columns]

    col_gap = random.randint(15, 30)

    html = f'<div class="layout-node multi-column" data-label="multi-column" style="display: grid; grid-template-columns: repeat({columns}, 1fr); gap: {col_gap}px; height: 100%; width: 100%; box-sizing: border-box; padding-bottom: 20px;">'
    for chunk in chunks:
        html += f"""
        <div class="layout-node paragraph" data-label="paragraph" 
             style="height: 100%; width: 100%; font-family: '{font}'; color: {color}; font-size:{font_size}px; 
                    text-align: justify; overflow: hidden; line-height: 1.8;">
            {chunk}
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

    # Notice how the wrapper is a layout-node, and the children are also layout-nodes
    return f"""
    <div class="layout-node figure" data-label="figure" 
         style="height: 100%; width: 100%; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; padding-bottom: 15px;">
        <div class="layout-node figure-image" data-label="figure-image" style="flex-grow: 1; background:#e2e8f0; border:2px solid #64748b; display:flex; align-items:center; justify-content:center; box-sizing: border-box; overflow: hidden;">
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

    # Notice how the wrapper is a layout-node, and the TH/TD cells are also layout-nodes
    html = f'<div class="layout-node table-wrapper" data-label="table" style="height: 100%; width: 100%; overflow: hidden; box-sizing: border-box; padding-bottom: 15px;">'
    html += f'<table style="height: 100%; width: 100%; table-layout: fixed; border-collapse: collapse; font-family: \'{font}\'; color: {color}; box-sizing: border-box;">'

    for r in range(rows):
        html += "<tr>"
        for c in range(cols):
            if r == 0:
                html += f'<th class="layout-node table-cell" data-label="table-cell" style="border: 2px solid {color}; background-color: #f8fafc; padding: 10px 10px 16px 10px; font-size: 14px; overflow: hidden; box-sizing: border-box;">{get_real_arabic_text(1, 3)}</th>'
            else:
                html += f'<td class="layout-node table-cell" data-label="table-cell" style="border: 1px solid {color}; padding: 10px 10px 16px 10px; font-size: 14px; overflow: hidden; box-sizing: border-box;">{get_real_arabic_text(2, 8)}</td>'
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
            body {{
                width: 794px;
                height: 1123px;       
                margin: 0;
                padding: 40px;
                box-sizing: border-box;
                background-color: white;
                overflow: hidden;
            }}
            * {{
                box-sizing: border-box;
            }}
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
        if r == 0:
            col_layout = "1fr"
        else:
            col_layout = random.choice(["1fr", "1fr 1fr", "1fr 2fr", "2fr 1fr", "1fr 1fr 1fr"])

        cols = col_layout.split()
        html += f'<div style="display: grid; gap: 20px; grid-template-columns: {col_layout}; height: 100%;">'

        for _ in range(len(cols)):
            if r == 0:
                comp = gen_heading()
            else:
                comp_type = random.choices(["para", "table", "figure"], weights=[0.5, 0.25, 0.25])[0]

                if comp_type == "para":
                    inner_cols = random.choice([1, 1, 2, 3]) if len(cols) == 1 else 1
                    comp = gen_paragraph(columns=inner_cols)
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

        # The Javascript inside Playwright handles the DOM Hierarchy scanning
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

            // STEP 2: AUTO-FIT TEXT
            const textNodes = document.querySelectorAll('.paragraph, .heading, th, td');
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

            // STEP 3: HIERARCHICAL RTL EXTRACTION
            const data = [];

            // Recursive function to step into tables/figures/columns
            function extractNode(node, prefix) {
                const rect = node.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                // Find direct children ONLY (avoids double counting nested items)
                const allChildren = Array.from(node.querySelectorAll('.layout-node'));
                const directChildren = allChildren.filter(child => {
                    let p = child.parentElement;
                    while (p && p !== node) {
                        if (p.classList.contains('layout-node')) return false;
                        p = p.parentElement;
                    }
                    return true;
                });

                // Extract text only if it's a leaf node (e.g. paragraph, cell, caption). Parent boxes will just map the zone.
                let extractedText = "";
                if (directChildren.length === 0 && node.getAttribute('data-label') !== 'figure-image') {
                    extractedText = node.innerText ? node.innerText.trim().replace(/\\s+/g, ' ') : "";
                }

                data.push({
                    label: node.getAttribute('data-label'),
                    text: extractedText,
                    reading_index: prefix,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    bottom: rect.bottom,
                    right: rect.right
                });

                // Dive into children (assigns 4.1, 4.2, etc.)
                directChildren.forEach((child, index) => {
                    extractNode(child, `${prefix}.${index + 1}`);
                });
            }

            // Find ROOT layout nodes (Boxes that have NO layout-node above them)
            const allLayoutNodes = Array.from(document.querySelectorAll('.layout-node'));
            const rootNodes = allLayoutNodes.filter(node => {
                let p = node.parentElement;
                while(p) {
                    if (p.classList.contains('layout-node')) return false;
                    p = p.parentElement;
                }
                return true;
            });

            // Execute recursively, starting at 1. Because the HTML is <dir="rtl">, 
            // the DOM natural order is inherently Top-To-Bottom, Right-to-Left!
            rootNodes.forEach((root, index) => {
                extractNode(root, `${index + 1}`);
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

    os.makedirs(DATASET_IMAGES_PATH, exist_ok=True)
    os.makedirs(DATASET_ANNOTATIONS_PATH, exist_ok=True)

    NUM_SAMPLES = 10

    print(f"Generating {NUM_SAMPLES} Perfected A4 templates...")
    for i in tqdm(range(NUM_SAMPLES)):
        html_string = generate_random_template()
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