"""Formal/administrative letter: letterhead, date, recipient line, salutation,
body paragraph(s), closing phrase and a signature block."""

import random
from core import assets, components, hybrid

NAME = "letter"
SIZE_PRESETS_MM = [(210, 297), (210, 297), (210, 297), (148, 210)]  # mostly A4, sometimes A5 memo


def generate(hybrid_html=""):
    width, height = assets.jittered_size(*random.choice(SIZE_PRESETS_MM))
    font = random.choice(assets.FONTS)

    letterhead = assets.get_real_arabic_text(2, 5)
    date_line = f"{random.choice(['الرباط', 'الدار البيضاء', 'فاس', 'مراكش'])}، في {random.randint(1,28):02d}/{random.randint(1,12):02d}/{random.randint(2023,2026)}"
    recipient = random.choice(assets.LETTER_OPENERS)
    subject = "الموضوع: " + assets.get_real_arabic_text(3, 8)
    intro = random.choice(assets.LETTER_INTROS)
    body_paras = [assets.get_real_arabic_text(60, 150) for _ in range(random.randint(1, 2))]
    closing = random.choice(assets.LETTER_CLOSINGS)
    signature_name = assets.get_real_arabic_name()

    def block(label, text, size=14, bold=False, align="right"):
        weight = "bold" if bold else "normal"
        return (f'<div class="layout-node autofit-text" data-label="{label}" '
                f'style="font-family:\'{font}\'; font-size:{size}px; font-weight:{weight}; text-align:{align}; '
                f'line-height:1.8; margin-bottom:12px; overflow:hidden;">{text}</div>')

    blocks = [
        block("letterhead", letterhead, size=20, bold=True, align="center"),
        block("date-line", date_line, size=13, align="left"),
        block("recipient", recipient, size=14, bold=True),
        block("subject-line", subject, size=13, bold=True),
        block("salutation", intro, size=14),
    ]
    for p in body_paras:
        blocks.append(block("body-paragraph", p, size=14, align="justify" if False else "right"))
    blocks.append(block("closing", closing, size=14))

    if hybrid_html:
        blocks.insert(len(blocks) - 1, hybrid.wrap_hybrid_block(hybrid_html))

    blocks.append(
        f'<div style="margin-top:30px; text-align:left;">'
        f'<div class="layout-node autofit-text" data-label="signature" '
        f'style="font-family:\'{font}\'; font-size:14px; font-weight:bold; overflow:hidden;">{signature_name}</div>'
        f'</div>'
    )

    flow = "".join(blocks)
    body = f'<div id="content-flow" style="width:100%; height:100%; padding:50px; box-sizing:border-box;">{flow}</div>'

    return {"width": width, "height": height, "body": body, "auto_height": False}
