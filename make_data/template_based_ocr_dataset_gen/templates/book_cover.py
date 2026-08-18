"""Front book cover: full-bleed art background, large title, author name,
occasional tagline and a small publisher mark."""

import random
from core import assets, components, hybrid

NAME = "book_cover"
SIZE_PRESETS_MM = [
    (152, 229),  # trade paperback
    (148, 210),  # A5 novel
    (110, 178),  # mass-market paperback
    (210, 276),  # large textbook-style
]


def generate(hybrid_html=""):
    base = random.choice(SIZE_PRESETS_MM)
    width, height = assets.jittered_size(*base)

    # Book cover is one of the few cases where title font IS the display font
    title_font = assets.get_page_title_font()
    body_font = assets.get_page_body_font()
    title_color = random.choice(["#ffffff", "#111111", "#fef3c7"])
    band_color = random.choice(["rgba(0,0,0,0.55)", "rgba(0,0,0,0.35)", "rgba(255,255,255,0.85)"])

    img_b64 = assets.random_image_b64()
    bg_html = (f'<img src="{img_b64}" style="width:100%; height:100%; object-fit:cover; display:block; position:absolute; inset:0;" />'
               if img_b64 else '<div style="position:absolute; inset:0; background:#94a3b8;"></div>')

    title_text = assets.get_real_arabic_title()
    author_text = assets.get_semantic_name()
    has_tagline = random.random() < 0.5
    tagline_html = (
        f'<div class="layout-node autofit-text" data-label="tagline" '
        f'style="font-family:\'{body_font}\'; font-size:13px; color:{title_color}; text-align:center; margin-top:8px; overflow:hidden;">{assets.get_real_arabic_text(4, 10)}</div>'
        if has_tagline else ""
    )

    hybrid_block = f'<div style="margin-top:10px; width:80%;">{hybrid.wrap_hybrid_block(hybrid_html, compact_margin=True)}</div>' if hybrid_html else ""

    body = f"""
    <div style="width:100%; height:100%; position:relative; overflow:hidden; background:white;">
        {bg_html}
        <div style="position:absolute; inset:0; background:{band_color}; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:24px; box-sizing:border-box; text-align:center;">
            <div class="layout-node autofit-text" data-label="book-title"
                 style="font-family:'{title_font}'; font-size:34px; font-weight:bold; color:{title_color}; line-height:1.3; overflow:hidden; max-width:100%;">{title_text}</div>
            {tagline_html}
            {hybrid_block}
        </div>
        <div style="position:absolute; bottom:18px; left:0; right:0; display:flex; justify-content:center;">
            <div class="layout-node autofit-text" data-label="author"
                 style="font-family:'{body_font}'; font-size:16px; font-weight:bold; color:{title_color}; background:rgba(0,0,0,0.0); overflow:hidden;">{author_text}</div>
        </div>
    </div>
    """

    return {"width": width, "height": height, "body": body, "auto_height": False}
