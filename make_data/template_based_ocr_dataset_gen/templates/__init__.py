"""
templates/__init__.py
=======================
Registry of every document template. Add a new template by dropping a
module in this folder with a `NAME` string and a
`generate(hybrid_html="") -> dict` function (see any existing template
for the expected dict shape: width, height, body, auto_height), then
register it below. generate.py never needs to change.
"""

from . import (
    a4_report,
    a4_charts,
    a4_paper,
    a4_image_gallery,
    a4_literary,
    business_card,
    book_cover,
    receipt,
    letter,
    minimalist,
    math_proof,
    id_card,
    invoice,
)

TEMPLATES = {
    a4_report.NAME: a4_report.generate,
    a4_charts.NAME: a4_charts.generate,
    a4_paper.NAME: a4_paper.generate,
    a4_image_gallery.NAME: a4_image_gallery.generate,
    a4_literary.NAME: a4_literary.generate,
    business_card.NAME: business_card.generate,
    book_cover.NAME: book_cover.generate,
    receipt.NAME: receipt.generate,
    letter.NAME: letter.generate,
    minimalist.NAME: minimalist.generate,
    math_proof.NAME: math_proof.generate,
    id_card.NAME: id_card.generate,
    invoice.NAME: invoice.generate,
}
