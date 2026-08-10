"""
core/render_engine.py
======================
Production rendering engine for dataset generation. Handles layout isolation,
KaTeX auto-scaling, overlap resolution, and precision bounding-box extraction.
"""

import json
from playwright.async_api import async_playwright

FONT_IMPORT_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Almarai:wght@400;700&family=Amiri:wght@400;700&family=Cairo:wght@400;700"
    "&family=Changa:wght@400;700&family=Tajawal:wght@400;700&family=Aref+Ruqaa:wght@400;700"
    "&family=Rakkas&family=Lalezar&family=Katibeh&family=Reem+Kufi:wght@400;700"
    "&family=El+Messiri:wght@400;700&family=Markazi+Text&family=Mada&family=Harmattan"
    "&display=swap"
)


def build_html_page(width, height, body_html, auto_height=False):
    """Wrap template HTML in a structured document with layout isolation rules."""
    height_css = f"min-height: {height}px;" if auto_height else f"height: {height}px;"
    overflow_css = "overflow: visible;" if auto_height else "overflow: hidden;"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@import url('{FONT_IMPORT_URL}');

* {{ 
    box-sizing: border-box; 
    overflow-wrap: break-word; 
    word-break: break-word; 
}}

html, body {{ 
    margin: 0; 
    padding: 0; 
    width: {width}px; 
}}

body {{
    width: {width}px;
    {height_css}
    background-color: white;
    {overflow_css}
    position: relative;
}}

/* LAYOUT ISOLATION: Enforce Block Formatting Context to prevent overlapping */
.layout-node, .block, .section, .theorem-box, header, footer {{
    display: flow-root !important;
    clear: both !important;
    position: relative;
    box-sizing: border-box;
}}

/* KATEX MATH FORMULA CONSTRAINTS */
.katex-display-math, .katex-display {{
    margin: 6px 0 !important;
    padding: 2px 0 !important;
    line-height: 1.2 !important;
    max-width: 100% !important;
    overflow-x: auto !important;
    overflow-y: hidden !important;
}}

.katex {{
    font-size: 0.95em !important;
    line-height: 1.2 !important;
    text-indent: 0 !important;
}}

/* MEDIA CONSTRAINTS */
img, canvas, svg, figure {{
    max-width: 100% !important;
    max-height: 100% !important;
    object-fit: contain !important;
    display: block;
}}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


# --------------------------------------------------------------
# In-browser extraction & auto-fix script
# --------------------------------------------------------------

EXTRACTION_SCRIPT = r"""
(params) => {
    const autoHeight = params.autoHeight;

    // STEP 1: Render KaTeX math elements
    document.querySelectorAll('.katex-display-math').forEach(el => {
        try {
            const rawMath = decodeURIComponent(escape(atob(el.getAttribute('data-math'))));
            katex.render(rawMath, el, {displayMode: true, throwOnError: false});
        } catch (e) {}
    });
    document.querySelectorAll('.katex-inline-math').forEach(el => {
        try {
            const rawMath = decodeURIComponent(escape(atob(el.getAttribute('data-math'))));
            katex.render(rawMath, el, {displayMode: false, throwOnError: false});
        } catch (e) {}
    });

    // STEP 2: KATEX AUTO-SCALER (Fixes Math Protrusion/Overflow)
    document.querySelectorAll('.katex-display-math, .katex-display').forEach(mathEl => {
        const parent = mathEl.parentElement;
        if (!parent) return;

        let currentScale = 1.0;
        while ((mathEl.scrollWidth > parent.clientWidth || mathEl.scrollHeight > mathEl.clientHeight + 2) && currentScale > 0.55) {
            currentScale -= 0.05;
            mathEl.style.fontSize = currentScale + 'em';
        }
    });

    // STEP 3: TABLE OVERFLOW FIX
    document.querySelectorAll('.table-wrapper').forEach(wrapper => {
        const table = wrapper.querySelector('table');
        if (table) {
            while (wrapper.scrollHeight > wrapper.clientHeight + 1 && table.rows.length > 1) {
                table.deleteRow(-1);
            }
        }
    });

    // STEP 4: AUTOFIT TEXT - Shrink overflowing leaf text nodes
    document.querySelectorAll('.autofit-text').forEach(node => {
        while ((node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1)
                && node.textContent.trim().split(/\s+/).length > 0) {
            let words = node.textContent.trim().split(/\s+/);
            if (words.length <= 1) { node.textContent = ""; break; }
            words.pop();
            node.textContent = words.join(' ');
        }
    });

    // STEP 5: SIBLING OVERLAP RESOLVER
    // Iterates through consecutive sibling nodes and adjusts vertical spacing if an overlap is detected.
    const allBlocks = Array.from(document.querySelectorAll('.layout-node'));
    for (let i = 0; i < allBlocks.length - 1; i++) {
        const current = allBlocks[i];
        const next = allBlocks[i + 1];

        if (current.parentElement === next.parentElement) {
            const r1 = current.getBoundingClientRect();
            const r2 = next.getBoundingClientRect();

            // Detect vertical collision
            if (r2.top < r1.bottom && r1.height > 0 && r2.height > 0) {
                const overlapPixels = (r1.bottom - r2.top) + 8; // 8px safety buffer
                const currentMargin = parseFloat(window.getComputedStyle(next).marginTop) || 0;
                next.style.marginTop = (currentMargin + overlapPixels) + 'px';
            }
        }
    }

    // STEP 6: UNIVERSAL OUT-OF-BOUNDS CROP
    if (!autoHeight) {
        const safeLeft = 0;
        const safeTop = 0;
        const safeRight = document.body.clientWidth;
        const safeBottom = document.body.clientHeight;
        const container = document.getElementById('content-flow') || document.body;

        for (let pass = 0; pass < 5; pass++) {
            let removedAny = false;
            Array.from(container.children).forEach(block => {
                if (['SCRIPT', 'STYLE', 'LINK'].includes(block.tagName)) return;

                const r = block.getBoundingClientRect();
                if (r.width === 0 || r.height === 0 ||
                    r.left < safeLeft - 4 || r.top < safeTop - 4 ||
                    r.right > safeRight + 4 || r.bottom > safeBottom + 4) {
                    block.remove();
                    removedAny = true;
                }
            });
            if (!removedAny) break;
        }
    }

    // STEP 7: MEASURE AUTO-HEIGHT
    let measuredHeight = null;
    if (autoHeight) {
        const flow = document.getElementById('content-flow') || document.body;
        measuredHeight = Math.ceil(flow.getBoundingClientRect().bottom + 20);
    }

    // STEP 8: EXTRACT BOUNDING BOXES
    const elements = document.querySelectorAll('.layout-node');
    const data = [];
    const canvasW = document.body.clientWidth;
    const canvasH = autoHeight ? (measuredHeight || document.body.clientHeight) : document.body.clientHeight;

    elements.forEach(el => {
        const rect = el.getBoundingClientRect();

        if (rect.width <= 0 || rect.height <= 0) return;

        // Skip nodes leaking past page edges
        if (!autoHeight && (rect.bottom > canvasH + 2 || rect.right > canvasW + 2 || rect.left < -2 || rect.top < -2)) {
            return;
        }

        const label = el.getAttribute('data-label') || 'unknown';
        const children = el.querySelectorAll('.layout-node');
        const isParent = children.length > 0;

        let extractedText = "";
        let extractedHtml = "";
        if (label === 'table') {
            const tbl = el.querySelector('table');
            if (tbl) extractedHtml = tbl.outerHTML;
        }

        if (!isParent && el.getAttribute('data-no-text') !== 'true') {
            // For equation nodes, decode the original LaTeX from data-math
            const mathB64 = el.getAttribute('data-math');
            if (mathB64) {
                try {
                    extractedText = decodeURIComponent(escape(atob(mathB64)));
                } catch (e) {
                    extractedText = el.innerText ? el.innerText.trim().replace(/\s+/g, ' ') : "";
                }
            } else {
                extractedText = el.innerText ? el.innerText.trim().replace(/\s+/g, ' ') : "";
            }
        }

        data.push({
            label: label,
            text: extractedText,
            html: extractedHtml,
            is_parent: isParent,
            x: Math.max(0, Math.round(rect.x)),
            y: Math.max(0, Math.round(rect.y)),
            width: Math.min(canvasW, Math.round(rect.width)),
            height: Math.min(canvasH, Math.round(rect.height)),
            bottom: Math.min(canvasH, Math.round(rect.bottom)),
            right: Math.min(canvasW, Math.round(rect.right))
        });
    });

    return {boxes: data, measuredHeight: measuredHeight};
}
"""


async def render_and_extract(html_content, width, height, output_image_path, output_json_path,
                              auto_height=False, meta=None, initial_auto_height_viewport=3200):
    """Render HTML and export (image, JSON annotation) pair."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        vp_height = initial_auto_height_viewport if auto_height else height
        page = await browser.new_page(viewport={"width": width, "height": vp_height})

        await page.set_content(html_content, wait_until="networkidle")

        result = await page.evaluate(EXTRACTION_SCRIPT, {"autoHeight": auto_height})
        boxes = result["boxes"]

        final_height = height
        if auto_height and result.get("measuredHeight"):
            final_height = max(120, min(result["measuredHeight"], initial_auto_height_viewport))
            await page.set_viewport_size({"width": width, "height": final_height})

        await page.screenshot(path=output_image_path)
        await browser.close()

        blocks = []
        tables = []
        images = []
        markdown_lines = []
        
        table_counter = 0
        img_counter = 0
        reading_idx = 1
        
        def get_block_type(lbl):
            if lbl in ['heading', 'theorem-title']: return 'title'
            if lbl == 'table': return 'table'
            if lbl in ['logo', 'barcode', 'figure-image', 'image-gallery']: return 'image'
            return 'text'

        for box in boxes:
            label = box.get("label", "unknown")
            is_parent = box.get("is_parent", False)
            content = box.get("text", "")
            
            blk_type = get_block_type(label)
            
            if label == "table":
                table_id = f"tbl-{table_counter}.html"
                table_html = box.get("html", "")
                
                table_word_scores = []
                import re
                tokens = re.split(r'(<[^>]+>)', table_html)
                current_pos = 0
                for token in tokens:
                    if token.startswith('<') and token.endswith('>'):
                        current_pos += len(token)
                    else:
                        for match in re.finditer(r'\s*\S+', token):
                            word = match.group()
                            idx = current_pos + match.start()
                            table_word_scores.append({
                                "text": word,
                                "confidence": 1.0,
                                "start_index": idx
                            })
                        current_pos += len(token)

                tables.append({
                    "id": table_id,
                    "content": table_html,
                    "format": "html",
                    "word_confidence_scores": table_word_scores
                })
                blocks.append({
                    "top_left_x": box["x"], "top_left_y": box["y"],
                    "bottom_right_x": box["right"], "bottom_right_y": box["bottom"],
                    "content": box.get("html", ""),
                    "type": "table",
                    "table_id": table_id,
                    "confidence_scores": None,
                    "reading_index": reading_idx
                })
                markdown_lines.append(f"\n[{table_id}]({table_id})\n")
                table_counter += 1
                reading_idx += 1
            elif blk_type == "image":
                # Include image bounding box; if it's a parent wrapper, we still want it
                if is_parent and label not in ['logo', 'image-gallery', 'figure-image']:
                    continue
                
                img_id = f"img-{img_counter}"
                images.append({
                    "id": img_id,
                    "top_left_x": box["x"], "top_left_y": box["y"],
                    "bottom_right_x": box["right"], "bottom_right_y": box["bottom"],
                    "reading_index": reading_idx
                })
                blocks.append({
                    "top_left_x": box["x"], "top_left_y": box["y"],
                    "bottom_right_x": box["right"], "bottom_right_y": box["bottom"],
                    "content": f"![image]({img_id})",
                    "type": "image",
                    "confidence_scores": None,
                    "reading_index": reading_idx
                })
                markdown_lines.append(f"\n![image]({img_id})\n")
                img_counter += 1
                reading_idx += 1
            elif not is_parent:
                if not content: continue
                blocks.append({
                    "top_left_x": box["x"], "top_left_y": box["y"],
                    "bottom_right_x": box["right"], "bottom_right_y": box["bottom"],
                    "content": content,
                    "type": blk_type,
                    "confidence_scores": None,
                    "reading_index": reading_idx
                })
                if blk_type == "title":
                    markdown_lines.append(f"## {content}")
                else:
                    markdown_lines.append(content)
                reading_idx += 1

        markdown_text = "\n".join(markdown_lines)
        
        mock_word_scores = []
        current_idx = 0
        for word in markdown_text.split():
            idx = markdown_text.find(word, current_idx)
            if idx != -1:
                mock_word_scores.append({
                    "text": word,
                    "confidence": 1.0,
                    "start_index": idx
                })
                current_idx = idx + len(word)

        payload = {
            "markdown": markdown_text,
            "images": images,
            "tables": tables,
            "hyperlinks": [],
            "header": None,
            "footer": None,
            "dimensions": {
                "dpi": 96,
                "height": final_height,
                "width": width
            },
            "confidence_scores": {
                "word_confidence_scores": mock_word_scores,
                "average_page_confidence_score": 1.0,
                "minimum_page_confidence_score": 1.0
            },
            "blocks": blocks
        }
        
        if meta:
            payload["meta"] = meta

        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)