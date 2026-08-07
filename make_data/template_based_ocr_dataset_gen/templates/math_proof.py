"""Standalone dense math page: just theorems / proofs / equations stacked one
after another, no title or abstract. Randomly a full dense page or a tight
auto-height 'notebook excerpt' snippet, for extra size variety."""

import random
from core import assets, components, hybrid

NAME = "math_proof"


def _full_page():
    width, height = assets.jittered_size(210, 297)
    blocks = []
    for _ in range(random.randint(8, 14)):
        blocks.append(components.gen_theorem_box() if random.random() < 0.6 else components.gen_display_equation())
    return width, height, blocks, False


def _snippet():
    width = assets.jitter(random.randint(480, 720))
    blocks = []
    for _ in range(random.randint(2, 4)):
        blocks.append(components.gen_theorem_box(compact=True) if random.random() < 0.5 else components.gen_display_equation())
    return width, 300, blocks, True


def generate(hybrid_html=""):
    if random.random() < 0.5:
        width, height, blocks, auto_height = _full_page()
    else:
        width, height, blocks, auto_height = _snippet()

    if hybrid_html:
        blocks.insert(random.randint(0, len(blocks)), hybrid.wrap_hybrid_block(hybrid_html))

    flow = "".join(blocks)
    pad = 40 if not auto_height else 20
    body = f'<div id="content-flow" style="width:100%; height:100%; padding:{pad}px; box-sizing:border-box; background:white;">{flow}</div>'

    return {"width": width, "height": height, "body": body, "auto_height": auto_height}
