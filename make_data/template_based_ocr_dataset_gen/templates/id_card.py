"""ID / membership card: photo placeholder, name, ID number, org name, barcode strip."""

import random
from core import assets, components, hybrid

NAME = "id_card"
BASE_MM = (90, 55)


def generate(hybrid_html=""):
    width, height = assets.jittered_size(*BASE_MM, pct=0.1)
    font = random.choice(assets.FONTS)
    color = random.choice(assets.COLORS)

    org_name = assets.get_real_arabic_text(2, 4)
    holder_name = assets.get_real_arabic_name()
    id_number = "-".join(str(random.randint(1000, 9999)) for _ in range(2))

    photo_html = (
        '<div class="layout-node" data-label="photo-placeholder" data-no-text="true" '
        'style="width:44px; height:56px; background:#cbd5e1; border:1px solid #94a3b8; flex-shrink:0;"></div>'
    )

    hybrid_block = hybrid.wrap_hybrid_block(hybrid_html, compact_margin=True) if hybrid_html else ""

    body = f"""
    <div style="width:100%; height:100%; box-sizing:border-box; padding:10px; background:white; display:flex; flex-direction:column; justify-content:space-between;">
        <div class="layout-node autofit-text" data-label="org-name"
             style="font-family:'{font}'; font-weight:bold; font-size:12px; color:{color}; text-align:center; overflow:hidden;">{org_name}</div>
        <div style="display:flex; gap:8px; align-items:center;">
            {photo_html}
            <div style="flex-grow:1;">
                <div class="layout-node autofit-text" data-label="card-title"
                     style="font-family:'{font}'; font-size:13px; font-weight:bold; overflow:hidden;">{holder_name}</div>
                <div class="layout-node autofit-text" data-label="id-number"
                     style="font-family:'{font}'; font-size:11px; direction:ltr; text-align:right; margin-top:4px; overflow:hidden;">{id_number}</div>
            </div>
        </div>
        {hybrid_block}
        {components.gen_barcode(compact=True)}
    </div>
    """

    return {"width": width, "height": height, "body": body, "auto_height": False}
