"""Business card: small logo mark + name / role / contact lines. Landscape by
default (standard 85x55mm card), occasionally portrait."""

import random
from core import assets, components, hybrid

NAME = "business_card"
BASE_MM_LANDSCAPE = (85, 55)
BASE_MM_PORTRAIT = (55, 85)


def generate(hybrid_html=""):
    portrait = random.random() < 0.2
    base = BASE_MM_PORTRAIT if portrait else BASE_MM_LANDSCAPE
    width, height = assets.jittered_size(*base, pct=0.1)

    font = assets.get_page_body_font()
    color = random.choice(assets.COLORS)
    logo_side = random.choice(["flex-start", "flex-end"])

    name_text = assets.get_semantic_name()
    role_text = assets.get_semantic_job_title()
    contact1 = assets.random_fake_phone()
    # Contact 2: org name for realism
    contact2 = assets.get_semantic_org()

    logo_html = components.gen_logo(compact=True)
    hybrid_block = f'<div style="margin-top:6px;">{hybrid.wrap_hybrid_block(hybrid_html, compact_margin=True)}</div>' if hybrid_html else ""

    body = f"""
    <div style="width:100%; height:100%; box-sizing:border-box; padding:14px; background:white;
                display:flex; flex-direction:column; justify-content:space-between; align-items:{logo_side};">
        {logo_html}
        <div style="width:100%;">
            <div class="layout-node autofit-text" data-label="card-title"
                 style="font-family:'{font}'; font-weight:bold; font-size:16px; color:{color}; overflow:hidden;">{name_text}</div>
            <div class="layout-node autofit-text" data-label="card-role"
                 style="font-family:'{font}'; font-size:11px; color:#555; margin-top:2px; overflow:hidden;">{role_text}</div>
            <div class="layout-node autofit-text" data-label="contact-line"
                 style="font-family:'{font}'; font-size:10px; color:#333; margin-top:6px; direction:ltr; text-align:right; overflow:hidden;">{contact1}</div>
            <div class="layout-node autofit-text" data-label="contact-line"
                 style="font-family:'{font}'; font-size:10px; color:#333; overflow:hidden;">{contact2}</div>
        </div>
        {hybrid_block}
    </div>
    """

    return {"width": width, "height": height, "body": body, "auto_height": False}
