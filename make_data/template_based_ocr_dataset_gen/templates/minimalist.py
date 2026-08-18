"""Minimalist design: logo mark, then centered text in the middle of an
otherwise empty canvas. Covers posters / social-post style single-focus layouts."""

import random
from core import assets, components, hybrid

NAME = "minimalist"
SIZE_PRESETS_PX = [
    (700, 700),   # square social post
    (600, 900),   # portrait poster
    (1000, 500),  # landscape banner
]


def generate(hybrid_html=""):
    base = random.choice(SIZE_PRESETS_PX)
    width, height = assets.jittered_px(*base)

    bg_color = random.choice(["#ffffff", "#0f172a", "#f8fafc", "#111111"])
    text_color = "#ffffff" if bg_color in ("#0f172a", "#111111") else random.choice(assets.COLORS)
    # Title font for the main display text, body font for sub-text
    title_font = assets.get_page_title_font()
    body_font = assets.get_page_body_font()

    main_text = assets.get_real_arabic_title()
    has_subtext = random.random() < 0.55
    subtext_html = (
        f'<div class="layout-node autofit-text" data-label="subtext" '
        f'style="font-family:\'{body_font}\'; font-size:15px; color:{text_color}; margin-top:10px; text-align:center; overflow:hidden;">{assets.get_real_arabic_text(3, 8)}</div>'
        if has_subtext else ""
    )

    hybrid_block = f'<div style="margin-top:16px;">{hybrid.wrap_hybrid_block(hybrid_html, compact_margin=True)}</div>' if hybrid_html else ""

    body = f"""
    <div style="width:100%; height:100%; background:{bg_color}; box-sizing:border-box;
                display:flex; flex-direction:column; align-items:center; justify-content:center; padding:40px;">
        {components.gen_logo()}
        <div class="layout-node autofit-text" data-label="minimalist-title"
             style="font-family:'{title_font}'; font-size:30px; font-weight:bold; color:{text_color};
                    margin-top:22px; text-align:center; overflow:hidden; max-width:90%;">{main_text}</div>
        {subtext_html}
        {hybrid_block}
    </div>
    """

    return {"width": width, "height": height, "body": body, "auto_height": False}
