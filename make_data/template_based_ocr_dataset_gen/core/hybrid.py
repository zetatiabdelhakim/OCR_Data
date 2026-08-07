"""
core/hybrid.py
================
The "chaotic mixing" layer: with some probability, a randomly chosen
*foreign* snippet (a chart, an equation, a quote, a mini table, a small
figure) gets dropped into whatever template was picked - a chart inside
a receipt, an equation on a book cover, a quote on a business card back
side, etc. Each template decides *where* it goes; this module only
decides *whether* it happens and *what* the snippet is.
"""

import random
from . import components

HYBRID_GENERATORS = {
    "chart": lambda: components.gen_chart(compact=True),
    "equation": lambda: components.gen_display_equation(compact=True),
    "quote": lambda: components.gen_quote(),
    "mini-table": lambda: components.gen_table(rows=random.randint(3, 4), cols=random.randint(2, 3), compact=True),
    "figure": lambda: components.gen_figure(compact=True),
    "theorem": lambda: components.gen_theorem_box(compact=True),
}

DEFAULT_HYBRID_PROBABILITY = 0.28


def maybe_pick_hybrid(probability=DEFAULT_HYBRID_PROBABILITY, exclude=None):
    """Returns (name, html) with `probability` chance, else (None, "").
    `exclude` can be a set of names to skip (e.g. a template avoiding
    injecting its own native content type into itself)."""
    if random.random() >= probability:
        return None, ""
    pool = [k for k in HYBRID_GENERATORS if not exclude or k not in exclude]
    if not pool:
        return None, ""
    name = random.choice(pool)
    return name, HYBRID_GENERATORS[name]()


def wrap_hybrid_block(html, compact_margin=False):
    """Wrap a hybrid snippet in a generic container so it still reports
    a sane bounding box even though it doesn't belong to the host
    template's normal component set."""
    margin = "6px 0" if compact_margin else "12px 0"
    return (f'<div class="layout-node" data-label="hybrid-insert" '
            f'style="margin: {margin}; break-inside: avoid; box-sizing: border-box;">{html}</div>')
