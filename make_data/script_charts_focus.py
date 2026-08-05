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
        print(f"Loading text from {TEXT_FILE_PATH}...")
        with open(TEXT_FILE_PATH, 'r', encoding='utf-8') as f:
            CORPUS_WORDS = f.read().split()
    else:
        raise FileNotFoundError(f"{TEXT_FILE_PATH} not found.")

    if os.path.exists(IMAGE_FOLDER_PATH):
        print(f"Scanning images in {IMAGE_FOLDER_PATH}...")
        valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        IMAGE_PATHS = [
            os.path.join(IMAGE_FOLDER_PATH, f)
            for f in os.listdir(IMAGE_FOLDER_PATH)
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
    if not mime_type:
        mime_type = "image/jpeg"
    with open(img_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:{mime_type};base64,{encoded_string}"


# ==========================================
# 2. LAYOUT COMPONENT GENERATORS
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


def gen_complex_paragraph():
    """Generates a paragraph containing inner h1/h2/h3 and floating images."""
    text = get_real_arabic_text(80, 250)
    font = random.choice(FONTS)
    color = random.choice(COLORS)
    font_size = random.choice([14, 16, 18])

    h_level = random.choice(["h1", "h2", "h3"])
    h_text = get_real_arabic_text(2, 6)

    img_html = ""
    if IMAGE_PATHS and random.random() > 0.3:  # 70% chance to include a floating image
        img_path = random.choice(IMAGE_PATHS)
        img_b64 = get_image_base64(img_path)
        float_dir = random.choice(["right", "left"])
        margin_style = "margin: 0 0 10px 15px;" if float_dir == "right" else "margin: 0 15px 10px 0;"

        img_html = f"""
        <div class="layout-node float-image" data-label="figure" style="float: {float_dir}; width: 40%; {margin_style} border: 1px solid #94a3b8; border-radius: 4px; overflow: hidden; background: #e2e8f0; padding: 4px; box-sizing: border-box;">
            <img src="{img_b64}" style="width: 100%; height: auto; display: block;" />
            <div class="layout-node figure-caption" data-label="figure-caption" style="text-align:center; font-size: 12px; margin-top: 4px; color: #334155; font-weight: bold;">شكل توضيحي: {get_real_arabic_text(2, 4)}</div>
        </div>
        """

    return f"""
    <div class="layout-node complex-paragraph" data-label="paragraph" 
         style="height: 100%; width: 100%; font-family: '{font}'; color: {color}; font-size:{font_size}px; 
                text-align: justify; overflow: hidden; line-height: 1.8; box-sizing: border-box; padding-bottom: 20px;">
        <{h_level} class="layout-node" data-label="heading" style="margin-top: 0; margin-bottom: 10px; font-size: {font_size + 6}px; color: {random.choice(COLORS)};">{h_text}</{h_level}>
        {img_html}
        <span class="complex-text">{text}</span>
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


def gen_chart():
    """Generates 1 of 15 distinct Chart.js types to ensure high scientific diversity."""
    chart_id = f"chart_{random.randint(10000, 99999)}"
    labels = [f"'{get_real_arabic_text(1, 2)}'" for _ in range(5)]
    data1 = [random.randint(10, 100) for _ in range(5)]
    data2 = [random.randint(10, 100) for _ in range(5)]

    chart_configs = [
        f"type: 'bar', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'Dataset 1', data: {data1}, backgroundColor: 'rgba(54, 162, 235, 0.6)'}}]}}",
        f"type: 'bar', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'D1', data: {data1}, backgroundColor: '#ff6384'}}]}}, options: {{indexAxis: 'y'}}",
        f"type: 'bar', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'D1', data: {data1}, backgroundColor: '#36a2eb'}}, {{label: 'D2', data: {data2}, backgroundColor: '#ffce56'}}]}}, options: {{scales: {{x: {{stacked: true}}, y: {{stacked: true}}}}}}",
        f"type: 'line', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'Trend', data: {data1}, borderColor: '#4bc0c0', tension: 0.1}}]}}",
        f"type: 'line', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'Area', data: {data1}, borderColor: '#9966ff', backgroundColor: 'rgba(153, 102, 255, 0.2)', fill: true}}]}}",
        f"type: 'line', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'Steps', data: {data1}, borderColor: '#ff9f40', stepped: true}}]}}",
        f"type: 'line', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'Y1', data: {data1}, yAxisID: 'y'}}, {{label: 'Y2', data: {data2}, yAxisID: 'y1'}}]}}, options: {{scales: {{y: {{type: 'linear', position: 'left'}}, y1: {{type: 'linear', position: 'right'}}}}}}",
        f"type: 'pie', data: {{labels: [{','.join(labels)}], datasets: [{{data: {data1}, backgroundColor: ['#ff6384', '#36a2eb', '#cc65fe', '#ffce56', '#4bc0c0']}}]}}",
        f"type: 'doughnut', data: {{labels: [{','.join(labels)}], datasets: [{{data: {data2}, backgroundColor: ['#ff6384', '#36a2eb', '#cc65fe', '#ffce56', '#4bc0c0']}}]}}",
        f"type: 'doughnut', data: {{labels: [{','.join(labels)}], datasets: [{{data: {data1}, backgroundColor: ['#ff6384', '#36a2eb', '#cc65fe', '#ffce56', '#4bc0c0']}}]}}, options: {{circumference: 180, rotation: -90}}",
        f"type: 'radar', data: {{labels: [{','.join(labels)}], datasets: [{{label: 'Metrics', data: {data1}, backgroundColor: 'rgba(255, 99, 132, 0.2)', borderColor: '#ff6384'}}]}}",
        f"type: 'polarArea', data: {{labels: [{','.join(labels)}], datasets: [{{data: {data1}, backgroundColor: ['rgba(255, 99, 132, 0.5)', 'rgba(54, 162, 235, 0.5)', 'rgba(255, 206, 86, 0.5)', 'rgba(75, 192, 192, 0.5)', 'rgba(153, 102, 255, 0.5)']}}]}}",
        f"type: 'scatter', data: {{datasets: [{{label: 'Scatter', data: [{{x: 10, y: 20}}, {{x: 15, y: 10}}, {{x: 20, y: 30}}, {{x: 25, y: 5}}, {{x: 30, y: 15}}], backgroundColor: '#ff6384'}}]}}",
        f"type: 'bubble', data: {{datasets: [{{label: 'Bubble', data: [{{x: 10, y: 20, r: 15}}, {{x: 15, y: 10, r: 10}}, {{x: 20, y: 30, r: 25}}, {{x: 25, y: 5, r: 5}}], backgroundColor: '#36a2eb'}}]}}",
        f"type: 'bar', data: {{labels: [{','.join(labels)}], datasets: [{{type: 'line', label: 'Target', data: {data2}, borderColor: '#cc65fe'}}, {{type: 'bar', label: 'Actual', data: {data1}, backgroundColor: '#ffce56'}}]}}"
    ]

    config = random.choice(chart_configs)

    return f"""
    <div class="layout-node chart-wrapper" data-label="chart" style="height: 100%; width: 100%; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; padding-bottom: 15px;">
        <div style="text-align: center; font-family: '{random.choice(FONTS)}'; font-weight: bold; margin-bottom: 5px;">شكل إحصائي: {get_real_arabic_text(2, 5)}</div>
        <div style="flex-grow: 1; position: relative; width: 100%; height: 100%;">
            <canvas id="{chart_id}"></canvas>
        </div>
        <script>
            new Chart(document.getElementById('{chart_id}'), {{
                {config},
                options: Object.assign({{ animation: false, maintainAspectRatio: false }}, {config.split('options: ')[1] if 'options: ' in config else '{}'})
            }});
        </script>
    </div>
    """


# ==========================================
# 3. PAGE TEMPLATE BUILDER
# ==========================================

def build_html_page(grid_html):
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
        col_layout = "1fr" if r == 0 else random.choice(["1fr", "1fr 1fr", "1fr 2fr", "2fr 1fr", "1fr 1fr 1fr"])
        cols = col_layout.split()

        html += f'<div style="display: grid; gap: 20px; grid-template-columns: {col_layout}; height: 100%;">'

        for _ in range(len(cols)):
            if r == 0:
                comp = gen_heading()
            else:
                comp_type = random.choices(
                    ["complex_para", "table", "chart"],
                    weights=[0.5, 0.2, 0.3]
                )[0]

                if comp_type == "complex_para":
                    comp = gen_complex_paragraph()
                elif comp_type == "table":
                    comp = gen_table(rows=random.randint(5, 10), cols=random.randint(2, 4))
                else:
                    comp = gen_chart()

            html += f'<div style="height: 100%; overflow: hidden; display: flex; flex-direction: column;">{comp}</div>'

        html += '</div>'
    html += '</div>'
    return build_html_page(html)


# ==========================================
# 4. PLAYWRIGHT EXTRACTION ENGINE
# ==========================================

def assign_block_preserving_index(boxes):
    """
    Respects native DOM block order.
    Parents get -1. Leaf content children get sequential 1, 2, 3...
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
            // STEP 0: Inject missing layout-node classes to inner elements so Playwright sees them.
            // This fixes the complex-paragraph issue without changing Python HTML logic.
            document.querySelectorAll('.complex-text').forEach(el => {
                el.classList.add('layout-node');
                if(!el.getAttribute('data-label')) el.setAttribute('data-label', 'paragraph');
            });
            document.querySelectorAll('.float-image img').forEach(el => {
                el.classList.add('layout-node');
                el.setAttribute('data-label', 'image');
            });

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
            const textNodes = document.querySelectorAll('.complex-text, .paragraph, .heading, th, td, h1, h2, h3');
            textNodes.forEach(node => {
                const container = node.closest('.complex-paragraph') || node;
                while ((container.scrollHeight > container.clientHeight + 1 || container.scrollWidth > container.clientWidth + 1) && node.textContent.trim().split(/\\s+/).length > 0) {
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

            // STEP 3: NATIVE DOM EXTRACTION (PRESERVES BLOCK-BY-BLOCK FLOW)
            const elements = document.querySelectorAll('.layout-node');
            const data = [];

            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                const label = el.getAttribute('data-label');

                // Intelligently identify parents: if it contains inner layout-nodes, it's a wrapper.
                const children = el.querySelectorAll('.layout-node');
                const isParent = children.length > 0;

                // Extract text only if it's a leaf node. Skip pulling raw text for visuals.
                let extractedText = "";
                if (!isParent && label !== 'image' && label !== 'figure-image' && label !== 'chart') {
                    extractedText = el.innerText ? el.innerText.trim().replace(/\\s+/g, ' ') : "";
                }

                data.push({
                    label: label,
                    text: extractedText,
                    is_parent: isParent, // Consumed by Python
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

        # Apply strict Python-side indexing (-1 for parents, 1,2,3 for children)
        bounding_boxes = assign_block_preserving_index(bounding_boxes)

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

    NUM_SAMPLES = 20

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