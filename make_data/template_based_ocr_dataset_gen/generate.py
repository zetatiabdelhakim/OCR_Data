"""
generate.py
============
Single entry point for the whole dataset. Run this, not the individual
template modules.

    python generate.py

Each sample:
  1. picks ONE document template uniformly at random (no fixed weights -
     "chaotic" mix, per design decision)
  2. with HYBRID_PROBABILITY chance, also picks a random foreign snippet
     (chart / equation / quote / mini-table / figure / theorem) and asks
     the template to embed it somewhere sensible
  3. renders it with Playwright and writes the PNG + JSON pair

Expected local layout (same as the original single-purpose scripts):
    shamela_1M_words.txt      <- Arabic text corpus
    nature_images/            <- folder of photos used for figures/covers
    dataset/images/            <- output PNGs (created automatically)
    dataset/annotations/       <- output JSONs (created automatically)
"""

import os
import random
import asyncio
from tqdm import tqdm

from core import assets
from core.render_engine import build_html_page, render_and_extract
from core.hybrid import maybe_pick_hybrid
from templates import TEMPLATES

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

NUM_SAMPLES = 200
HYBRID_PROBABILITY = 0.28


async def generate_one(index):
    template_name = random.choice(list(TEMPLATES))
    generate_fn = TEMPLATES[template_name]

    # Do not inject large hybrid blocks into tiny cards, it ruins their layouts
    if template_name in ["id_card", "business_card"]:
        hybrid_name, hybrid_html = None, ""
    else:
        hybrid_name, hybrid_html = maybe_pick_hybrid(probability=HYBRID_PROBABILITY)

    spec = generate_fn(hybrid_html=hybrid_html)
    html_page = build_html_page(spec["width"], spec["height"], spec["body"], auto_height=spec["auto_height"])

    img_path = os.path.join(assets.DATASET_IMAGES_PATH, f"sample_{index:07d}.png")
    json_path = os.path.join(assets.DATASET_ANNOTATIONS_PATH, f"sample_{index:07d}.json")

    await render_and_extract(
        html_page, spec["width"], spec["height"], img_path, json_path,
        auto_height=spec["auto_height"],
        meta={"template": template_name, "hybrid": hybrid_name},
    )


async def main():
    assets.load_assets()
    os.makedirs(assets.DATASET_IMAGES_PATH, exist_ok=True)
    os.makedirs(assets.DATASET_ANNOTATIONS_PATH, exist_ok=True)

    print(f"Generating {NUM_SAMPLES} samples across {len(TEMPLATES)} templates: {', '.join(TEMPLATES)}")
    for i in tqdm(range(NUM_SAMPLES)):
        await generate_one(i)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(main())
