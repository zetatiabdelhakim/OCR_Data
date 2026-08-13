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

from dotenv import load_dotenv
from datasets import load_dataset
from core.text_provider import DocumentContext, current_document

from core import assets
from core.render_engine import build_html_page, render_and_extract
from core.hybrid import maybe_pick_hybrid
from templates import TEMPLATES

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

NUM_SAMPLES = 2000
HYBRID_PROBABILITY = 0.28
MAXIMUM_NUM_OF_WORKERS = 10
WORKERS = min(os.cpu_count() or 4, MAXIMUM_NUM_OF_WORKERS) 
NUM_BOOKS_TO_FETCH = 7
REFRESH_INTERVAL = 1000


async def generate_one(browser, index, books_pool):
    doc_ctx = DocumentContext(books_pool)
    token = current_document.set(doc_ctx)
    try:
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
    finally:
        current_document.reset(token)


async def worker_task(indices, queue, books_pool):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for index in indices:
            try:
                await generate_one(browser, index, books_pool)
            except Exception as e:
                print(f"Error generating sample {index}: {e}")
            finally:
                queue.put(1)
        await browser.close()


def worker_process(indices, queue, books_pool):
    try:
        asyncio.run(worker_task(indices, queue, books_pool))
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(worker_task(indices, queue, books_pool))


def init_worker():
    # Only load heavy assets once per worker process!
    assets.load_assets()


def main():
    os.makedirs(assets.DATASET_IMAGES_PATH, exist_ok=True)
    os.makedirs(assets.DATASET_ANNOTATIONS_PATH, exist_ok=True)

    print(f"Generating {NUM_SAMPLES} samples across {len(TEMPLATES)} templates using {WORKERS} workers: {', '.join(TEMPLATES)}")
    indices = list(range(NUM_SAMPLES))
    batches = [indices[i:i + REFRESH_INTERVAL] for i in range(0, len(indices), REFRESH_INTERVAL)]
    
    manager = multiprocessing.Manager()
    queue = manager.Queue()
    
    load_dotenv()
    print("Initializing dataset stream...")
    try:
        ds = load_dataset("MathematicianNLPer/hamela_books_text_full_ok", split="train", streaming=True, token=os.environ.get("HF_TOKEN"))
        # Randomize the seed so every execution gets completely different books
        ds = ds.shuffle(buffer_size=10000, seed=random.randint(0, 1000000))
        dataset_iterator = iter(ds)
    except Exception as e:
        print(f"Error loading dataset, using fallback text: {e}")
        dataset_iterator = None

    pbar = tqdm(total=NUM_SAMPLES, desc="Generating Samples")

    # Create the Pool ONCE for the entire generation to prevent reloading fonts/images
    with multiprocessing.Pool(processes=WORKERS, initializer=init_worker) as pool:
        for batch_indices in batches:
            books_pool = []
            if dataset_iterator:
                try:
                    for _ in range(NUM_BOOKS_TO_FETCH):
                        item = next(dataset_iterator)
                        text = item.get("text", list(item.values())[0])
                        books_pool.append(text)
                except StopIteration:
                    pass
                    
            if not books_pool:
                books_pool = ["نص تجريبي افتراضي للاختبار فقط. هذا النص يظهر عند فشل الاتصال بقاعدة البيانات."] * NUM_BOOKS_TO_FETCH

            chunk_size = (len(batch_indices) + WORKERS - 1) // WORKERS
            chunks = [batch_indices[i:i + chunk_size] for i in range(0, len(batch_indices), chunk_size)]

            results = []
            for chunk in chunks:
                results.append(pool.apply_async(worker_process, args=(chunk, queue, books_pool)))
                
            for _ in range(len(batch_indices)):
                queue.get()
                pbar.update(1)
                
            # Ensure the batch completes before fetching new books
            for r in results:
                r.get()

    pbar.close()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
