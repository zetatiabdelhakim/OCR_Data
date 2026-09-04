"""
core/render_engine.py
======================
Production rendering engine for dataset generation. Handles layout isolation,
KaTeX auto-scaling, overlap resolution, and precision bounding-box extraction.
"""

import os
import json
from playwright.async_api import async_playwright
from core import assets

_VENDOR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vendor")

try:
    with open(os.path.join(_VENDOR_DIR, "katex.min.css"), "r", encoding="utf-8") as f:
        KATEX_CSS = f.read()
    with open(os.path.join(_VENDOR_DIR, "katex.min.js"), "r", encoding="utf-8") as f:
        KATEX_JS = f.read()
    with open(os.path.join(_VENDOR_DIR, "chart.min.js"), "r", encoding="utf-8") as f:
        CHART_JS = f.read()
    
    # We replace URLs in katex.min.css if needed, but KaTeX fonts might still hit CDN.
    # To be fully offline for CSS, we leave the CSS content, it might try to load fonts.
    # It's better than blocking.
    CDN_HTML = f"""
<style>{KATEX_CSS}</style>
<script>{KATEX_JS}</script>
<script>{CHART_JS}</script>
"""
except Exception as e:
    print(f"Warning: could not load local vendor files: {e}. Using CDN.")
    CDN_HTML = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
"""

def build_html_page(width, height, body_html, auto_height=False):
    """Wrap template HTML in a structured document with layout isolation rules."""
    used_fonts_css = "".join([assets.FONT_FACE_DICT.get(f, "") for f in assets.FONTS if f in body_html])

    height_css = f"min-height: {height}px;" if auto_height else f"height: {height}px;"
    overflow_css = "overflow: visible;" if auto_height else "overflow: hidden;"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
{CDN_HTML}
<style>
{used_fonts_css}

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

/* LAYOUT ISOLATION: Only apply to nodes that are NOT inside flex/grid containers */
.layout-node, .block, .section, .theorem-box {{
    position: relative;
    box-sizing: border-box;
    min-height: 0;
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
    // Uses the PARENT's constrained height as the reference when the node itself
    // has no fixed height (e.g. inline spans, unconstrained divs).
    document.querySelectorAll('.autofit-text').forEach(node => {
        // Determine the effective bounding container
        const parent = node.parentElement;
        if (!parent) return;
        const parentRect = parent.getBoundingClientRect();
        const nodeRect = node.getBoundingClientRect();

        // Check: does the node overflow its parent vertically or horizontally?
        const isOverflowingParent = () => {
            const nr = node.getBoundingClientRect();
            const pr = parent.getBoundingClientRect();
            return (nr.bottom > pr.bottom + 2) || (nr.right > pr.right + 2) ||
                   (node.scrollHeight > node.clientHeight + 1) ||
                   (node.scrollWidth > node.clientWidth + 1);
        };

        let safety = 500;
        while (isOverflowingParent() && safety-- > 0) {
            let words = node.textContent.trim().split(/\s+/);
            if (words.length <= 1) { node.textContent = ""; break; }
            words.pop();
            node.textContent = words.join(' ');
        }
    });

    // STEP 5: GLOBAL OVERLAP RESOLVER
    // Remove any block that geometrically overlaps an earlier block by >20% of the smaller area.
    // This catches edge cases where CSS grids or footers collide without sharing a parent.
    const allBlocks = Array.from(document.querySelectorAll('.layout-node'));
    const keptRects = [];
    
    for (let i = 0; i < allBlocks.length; i++) {
        const current = allBlocks[i];
        if (current.style.display === 'none') continue;
        
        const r1 = current.getBoundingClientRect();
        if (r1.width <= 0 || r1.height <= 0) continue;
        
        // Skip parent nodes (they naturally overlap their children)
        if (current.querySelectorAll('.layout-node').length > 0) {
            continue; // We only check leaf nodes against each other
        }
        
        let overlaps = false;
        for (const r2 of keptRects) {
            const ox = Math.max(0, Math.min(r1.right, r2.right) - Math.max(r1.left, r2.left));
            const oy = Math.max(0, Math.min(r1.bottom, r2.bottom) - Math.max(r1.top, r2.top));
            const overlapArea = ox * oy;
            
            if (overlapArea > 0) {
                const area1 = r1.width * r1.height;
                const area2 = r2.width * r2.height;
                const minArea = Math.min(area1, area2);
                
                if (overlapArea > 0.20 * minArea) {
                    overlaps = true;
                    break;
                }
            }
        }
        
        if (overlaps) {
            current.remove(); // Remove from DOM entirely
        } else {
            keptRects.push(r1);
        }
    }

    // STEP 6: STRICT OUT-OF-BOUNDS & COLLAPSED NODE CROP
    // Remove any layout-node that overflows its bounding containers or the page.
    for (let pass = 0; pass < 5; pass++) {
        let removedAny = false;
        document.querySelectorAll('.layout-node').forEach(block => {
            const r = block.getBoundingClientRect();
            let clipped = false;

            if (r.width < 12 || r.height < 12) {
                clipped = true;
            } else {
                let current = block.parentElement;
                while (current && current !== document.body && current !== document.documentElement) {
                    const style = window.getComputedStyle(current);
                    if (style.overflow !== 'visible' && style.overflow !== '') {
                        const pr = current.getBoundingClientRect();
                        
                        // Check if block bleeds outside this restricted container
                        if (r.top < pr.top - 1 || r.bottom > pr.bottom + 1 || 
                            r.left < pr.left - 1 || r.right > pr.right + 1) {
                            
                            // Safe handling for headers and footers (allow 3px for borders/rounding)
                            const label = block.getAttribute('data-label') || '';
                            if (label === 'header' || label === 'footer') {
                                if (r.top < pr.top - 3 || r.bottom > pr.bottom + 3 ||
                                    r.left < pr.left - 3 || r.right > pr.right + 3) {
                                    clipped = true;
                                    break;
                                }
                            } else {
                                clipped = true;
                                break;
                            }
                        }
                    }
                    current = current.parentElement;
                }
                
                // If not autoHeight, also strictly check page boundaries (the body)
                if (!autoHeight && !clipped) {
                    const safeRight = document.body.clientWidth;
                    const safeBottom = document.body.clientHeight;
                    
                    const label = block.getAttribute('data-label') || '';
                    const tolerance = (label === 'header' || label === 'footer') ? 3 : 1;
                    
                    if (r.bottom > safeBottom + tolerance || r.top < -tolerance ||
                        r.right > safeRight + tolerance || r.left < -tolerance) {
                        clipped = true;
                    }
                }
            }

            if (clipped) {
                block.remove();
                removedAny = true;
            }
        });
        if (!removedAny) break;
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

        // Clamp nodes that are partially visible (instead of dropping them entirely)
        // Only skip nodes that are COMPLETELY outside the page
        if (!autoHeight) {
            if (rect.top >= canvasH || rect.bottom <= 0 || rect.left >= canvasW || rect.right <= 0) {
                return; // Fully outside - skip
            }
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


async def render_and_extract(browser, html_content, width, height, output_image_path, output_json_path,
                              auto_height=False, meta=None, initial_auto_height_viewport=3200):
    """Render HTML and export (image, JSON annotation) pair."""
    vp_height = initial_auto_height_viewport if auto_height else height
    page = await browser.new_page(viewport={"width": width, "height": vp_height})

    try:
        try:
            # We use 'load' instead of 'networkidle' because when spawning 10 workers rendering thousands
            # of pages, CDNs (like Google Fonts or jsdelivr) will heavily throttle the IP, causing
            # stray font/script requests to hang and timeout. 'load' ensures the critical DOM is ready.
            await page.set_content(html_content, wait_until="load", timeout=25000)
        except Exception as e:
            if "Timeout" in str(e):
                # If it still times out on 'load', the DOM is likely mostly there (just a hanging external asset).
                # We proceed with extraction instead of failing the sample.
                pass
            else:
                raise

        result = await page.evaluate(EXTRACTION_SCRIPT, {"autoHeight": auto_height})
        boxes = result["boxes"]

        final_height = height
        if auto_height and result.get("measuredHeight"):
            final_height = max(120, min(result["measuredHeight"], initial_auto_height_viewport))
            await page.set_viewport_size({"width": width, "height": final_height})

        await page.screenshot(path=output_image_path)
    finally:
        await page.close()

    blocks = []
    tables = []
    images = []
    markdown_lines = []
    
    global_header = None
    global_footer = None
    
    table_counter = 0
    img_counter = 0
    reading_idx = 1
    
    # Labels whose children should NOT be emitted as separate blocks
    # (the parent block already captures all their content)
    PARENT_ABSORBS_CHILDREN = {'table', 'logo'}
    
    def get_block_type(lbl):
        if lbl in ['heading', 'theorem-title']: return 'title'
        if lbl == 'table': return 'table'
        if lbl in ['logo', 'barcode', 'figure-image', 'image-gallery', 'photo-placeholder', 'chart']: return 'image'
        if lbl == 'header': return 'header'
        if lbl == 'footer': return 'footer'
        return 'text'
    
    # Build a set of labels that were emitted as absorbing parents,
    # then skip their children. We do this by tracking box indices.
    # First pass: identify which boxes are children of absorbing parents
    skip_indices = set()
    for i, box in enumerate(boxes):
        label = box.get('label', 'unknown')
        if label in PARENT_ABSORBS_CHILDREN and box.get('is_parent', False):
            # Find all child boxes that are geometrically inside this parent
            px, py = box['x'], box['y']
            pr, pb = box['right'], box['bottom']
            for j, child in enumerate(boxes):
                if j == i: continue
                cx, cy = child['x'], child['y']
                cr, cb = child['right'], child['bottom']
                # Child is inside parent if fully contained
                if cx >= px - 2 and cy >= py - 2 and cr <= pr + 2 and cb <= pb + 2:
                    skip_indices.add(j)

    for i, box in enumerate(boxes):
        if i in skip_indices:
            continue
        label = box.get("label", "unknown")
        is_parent = box.get("is_parent", False)
        content = box.get("text", "")
        blk_type = get_block_type(label)
        
        if label == "table":
            table_id = f"tbl-{table_counter}.html"
            table_html = box.get("html", "")
            table_word_scores = []
            import re
            
            # Clean table HTML to remove inline styles, classes, etc.
            def clean_attrs(m):
                tag = m.group(1)
                attrs = m.group(2)
                if not attrs:
                    return f"<{tag}>"
                keep = []
                for attr in ['rowspan', 'colspan']:
                    match = re.search(fr'{attr}="([^"]+)"', attrs)
                    if match:
                        keep.append(f'{attr}="{match.group(1)}"')
                if keep:
                    return f"<{tag} {' '.join(keep)}>"
                return f"<{tag}>"
            
            table_html = re.sub(r'<([a-zA-Z0-9]+)([^>]*)>', clean_attrs, table_html)

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
                "content": table_html,
                "type": "table",
                "table_id": table_id,
                "confidence_scores": None,
                "reading_index": reading_idx
            })
            markdown_lines.append(f"\n[{table_id}]({table_id})\n")
            table_counter += 1
            reading_idx += 1
        elif blk_type == "image":
            # Include image bounding box; if it's a parent wrapper, we still want it (e.g. logo)
            if is_parent and label not in ['logo']:
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
            
            if label == 'header': global_header = content
            if label == 'footer': global_footer = content
            
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
        "header": global_header,
        "footer": global_footer,
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
    
    # Always write meta — ensures consistent schema across originals and augmented images.
    # If no meta is passed, build a minimal default. The caller (generate.py) passes the full meta.
    if meta is None:
        meta = {}
    # Guarantee augmentation: null for originals (augmented images override this via transform_annotation)
    if "augmentation" not in meta:
        meta["augmentation"] = None
    # Guarantee language meta
    if "language" not in meta:
        meta["language"] = "ar"
        meta["script"] = "arabic"
        meta["direction"] = "rtl"
    payload["meta"] = meta

    # Compact separators, no indent: annotations are ~20% of the dataset's
    # bytes and indent=4 inflates them by roughly a third for no gain.
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))