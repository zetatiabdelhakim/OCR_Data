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
import multiprocessing
from tqdm import tqdm
from playwright.async_api import async_playwright

from core import assets
from core.render_engine import build_html_page, render_and_extract
from core.hybrid import maybe_pick_hybrid
from templates import TEMPLATES

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

NUM_SAMPLES = 1000
HYBRID_PROBABILITY = 0.28
WORKERS = os.cpu_count() or 4


async def generate_one(browser, index):
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
        browser, html_page, spec["width"], spec["height"], img_path, json_path,
        auto_height=spec["auto_height"],
        meta={"template": template_name, "hybrid": hybrid_name},
    )


async def worker_task(indices, queue):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for index in indices:
            await generate_one(browser, index)
            queue.put(1)
        await browser.close()


def worker_process(indices, queue):
    try:
        asyncio.run(worker_task(indices, queue))
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(worker_task(indices, queue))


def init_worker():
    assets.load_assets()


def main():
    os.makedirs(assets.DATASET_IMAGES_PATH, exist_ok=True)
    os.makedirs(assets.DATASET_ANNOTATIONS_PATH, exist_ok=True)

    print(f"Generating {NUM_SAMPLES} samples across {len(TEMPLATES)} templates using {WORKERS} workers: {', '.join(TEMPLATES)}")
    
    indices = list(range(NUM_SAMPLES))
    chunk_size = (NUM_SAMPLES + WORKERS - 1) // WORKERS
    chunks = [indices[i:i + chunk_size] for i in range(0, len(indices), chunk_size)]
    
    manager = multiprocessing.Manager()
    queue = manager.Queue()
    
    with multiprocessing.Pool(processes=WORKERS, initializer=init_worker) as pool:
        results = []
        for chunk in chunks:
            results.append(pool.apply_async(worker_process, args=(chunk, queue)))
            
        for _ in tqdm(range(NUM_SAMPLES), desc="Generating Samples"):
            queue.get()
            
        for r in results:
            r.get()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
