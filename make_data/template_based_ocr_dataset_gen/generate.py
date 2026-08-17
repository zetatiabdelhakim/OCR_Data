"""
generate.py
============
Single entry point for the whole dataset. Run this, not the individual
template modules.

    python generate.py

Each sample:
  1. picks ONE document template uniformly at random
  2. with HYBRID_PROBABILITY chance, also picks a random foreign snippet
  3. renders it with Playwright and writes the PNG + JSON pair
"""

import os
import random
import asyncio
import multiprocessing
import yaml
import shutil
import string
import time
from tqdm import tqdm
from playwright.async_api import async_playwright

from dotenv import load_dotenv
from datasets import load_dataset
from huggingface_hub import login, HfApi

from core.text_provider import DocumentContext, current_document
from core import assets
from core.render_engine import build_html_page, render_and_extract
from core.hybrid import maybe_pick_hybrid
from templates import TEMPLATES

# ------------------------------------------------------------------
# Load configuration
# ------------------------------------------------------------------
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

USER_NAME = config.get("user_name", "user")
REPO_ID = config.get("repo_id", "org/repo")
DESTINATION = config.get("destination", "lcl")
GLOBAL_LIMIT = config.get("global_limit", 50000)
USER_LOCAL_LIMIT = config.get("user_local_limit", 20000)
CHUNK_LIMIT = config.get("chunk_limit", 9000)
NUM_SAMPLES = config.get("num_samples", 2000)

WORKERS = config.get("workers", "auto")
MAXIMUM_NUM_OF_WORKERS = config.get("maximum_num_of_workers", 10)
if WORKERS == "auto":
    WORKERS = min(os.cpu_count() or 4, MAXIMUM_NUM_OF_WORKERS)

HYBRID_PROBABILITY = config.get("hybrid_probability", 0.28)
REFRESH_INTERVAL = config.get("refresh_interval", 1000)
NUM_BOOKS_TO_FETCH = config.get("num_books_to_fetch", 7)
TEXT_CORPUS_HF_ID = config.get("text_corpus_hf_id", "MathematicianNLPer/hamela_books_text_full_ok")
LOCAL_OUTPUT_DIR = config.get("local_output_dir", "./dataset_local_output")

STATE_FILE = "state.yaml"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "current_folder_name": "",
        "current_folder_count": 0,
        "local_total_pushed": 0
    }

def save_state(state):
    # Atomic save to prevent corruption, with retry for Windows
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(state, f)
    for _ in range(10):
        try:
            os.replace(temp_file, STATE_FILE)
            break
        except PermissionError:
            time.sleep(0.1)


async def generate_one(browser, index, books_pool, template_name, images_path, annotations_path):
    doc_ctx = DocumentContext(books_pool)
    token = current_document.set(doc_ctx)
    try:
        generate_fn = TEMPLATES[template_name]

        # Do not inject large hybrid blocks into tiny cards, it ruins their layouts
        if template_name in ["id_card", "business_card"]:
            hybrid_name, hybrid_html = None, ""
        else:
            hybrid_name, hybrid_html = maybe_pick_hybrid(probability=HYBRID_PROBABILITY)

        spec = generate_fn(hybrid_html=hybrid_html)
        html_page = build_html_page(spec["width"], spec["height"], spec["body"], auto_height=spec["auto_height"])

        img_path = os.path.join(images_path, f"sample_{index:07d}.png")
        json_path = os.path.join(annotations_path, f"sample_{index:07d}.json")

        await render_and_extract(
            browser, html_page, spec["width"], spec["height"], img_path, json_path,
            auto_height=spec["auto_height"],
            meta={"template": template_name, "hybrid": hybrid_name},
        )
    finally:
        current_document.reset(token)


async def worker_task(tasks, queue, books_pool):
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=True)
            for i, (index, template_name, images_path, annotations_path) in enumerate(tasks):
                # Relaunch browser periodically to prevent Node.js IPC pipe crashes
                if i > 0 and i % 30 == 0:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                    browser = await p.chromium.launch(headless=True)
                    
                try:
                    await generate_one(browser, index, books_pool, template_name, images_path, annotations_path)
                except Exception as e:
                    print(f"Error generating sample {index}: {e}")
                    if "Connection closed" in str(e) or "Target closed" in str(e):
                        try:
                            await browser.close()
                        except Exception:
                            pass
                        browser = await p.chromium.launch(headless=True)
                finally:
                    queue.put(1)
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass


def worker_process(tasks, queue, books_pool):
    try:
        asyncio.run(worker_task(tasks, queue, books_pool))
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(worker_task(tasks, queue, books_pool))


def init_worker():
    # Only load heavy assets once per worker process!
    assets.load_assets()


def get_global_count(api):
    print("Checking global dataset size on Hugging Face...")
    try:
        files = api.list_repo_files(repo_id=REPO_ID, repo_type="dataset")
        # approximate count based on .json files
        count = sum(1 for f in files if f.endswith('.json'))
        print(f"Current global dataset size: ~{count} samples.")
        return count
    except Exception as e:
        print(f"Error checking repo files (maybe repo doesn't exist yet): {e}")
        return 0


def generate_folder_name():
    random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
    return f"{USER_NAME}_{random_chars}"


def main():
    load_dotenv()
    
    hf_token = os.environ.get("HF_TOKEN")
    api = None
    if DESTINATION == "hf":
        if not hf_token:
            print("Error: HF_TOKEN is not set in .env. Required when destination is 'hf'.")
            return
        print("Logging in to Hugging Face...")
        login(token=hf_token)
        api = HfApi()
        
        global_count = get_global_count(api)
        if global_count >= GLOBAL_LIMIT:
            print(f"Global limit of {GLOBAL_LIMIT} reached ({global_count}). Exiting.")
            return
    
    state = load_state()
    
    if not state.get("current_folder_name"):
        state["current_folder_name"] = generate_folder_name()
        state["current_folder_count"] = 0
        save_state(state)
        
    print("Initializing dataset stream...")
    try:
        ds = load_dataset(TEXT_CORPUS_HF_ID, split="train", streaming=True, token=hf_token)
        # Randomize the seed so every execution gets completely different books
        ds = ds.shuffle(buffer_size=10000, seed=random.randint(0, 1000000))
        dataset_iterator = iter(ds)
    except Exception as e:
        print(f"Error loading dataset, using fallback text: {e}")
        dataset_iterator = None

    templates_list = list(TEMPLATES)
    manager = multiprocessing.Manager()
    queue = manager.Queue()
    
    total_generated_this_run = 0

    with multiprocessing.Pool(processes=WORKERS, initializer=init_worker) as pool:
        while total_generated_this_run < NUM_SAMPLES:
            state = load_state()
            folder_name = state["current_folder_name"]
            folder_count = state["current_folder_count"]
            local_total = state["local_total_pushed"]
            
            if folder_count >= CHUNK_LIMIT:
                temp_dir = os.path.abspath(f"./temp_generation_{folder_name}")
                print(f"Chunk limit ({CHUNK_LIMIT}) reached for folder {folder_name}. Processing upload/move...")
                if DESTINATION == "hf":
                    print(f"Uploading {temp_dir} to Hugging Face: data/{folder_name} ...")
                    try:
                        api.upload_folder(
                            folder_path=temp_dir,
                            path_in_repo=f"data/{folder_name}",
                            repo_id=REPO_ID,
                            repo_type="dataset"
                        )
                        print("Upload complete. Cleaning up local temp dir...")
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception as e:
                        print(f"Failed to upload to Hugging Face: {e}")
                        return
                else:
                    dest_path = os.path.join(LOCAL_OUTPUT_DIR, folder_name)
                    print(f"Moving {temp_dir} to {dest_path} ...")
                    os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)
                    shutil.move(temp_dir, dest_path)
                
                # Reset state for next chunk
                state["local_total_pushed"] += folder_count
                state["current_folder_name"] = generate_folder_name()
                state["current_folder_count"] = 0
                save_state(state)
                
                if DESTINATION == "hf":
                    global_count = get_global_count(api)
                    if global_count >= GLOBAL_LIMIT:
                        print(f"Global limit reached! ({global_count} >= {GLOBAL_LIMIT}). Exiting.")
                        break
                
                # Continue the loop with new folder
                continue
                
            user_historical_total = local_total + folder_count
            if user_historical_total >= USER_LOCAL_LIMIT:
                print(f"User local limit of {USER_LOCAL_LIMIT} reached (Historical Total: {user_historical_total}). Exiting.")
                break
                
            remaining_in_chunk = CHUNK_LIMIT - folder_count
            remaining_in_run = NUM_SAMPLES - total_generated_this_run
            remaining_allowed = USER_LOCAL_LIMIT - user_historical_total
            batch_size = min(remaining_in_chunk, remaining_in_run, REFRESH_INTERVAL, remaining_allowed)
            
            if batch_size <= 0:
                break
                
            temp_dir = os.path.abspath(f"./temp_generation_{folder_name}")
            images_path = os.path.join(temp_dir, "images")
            annotations_path = os.path.join(temp_dir, "annotations")
            
            os.makedirs(images_path, exist_ok=True)
            os.makedirs(annotations_path, exist_ok=True)
            
            print(f"--- Folder: {folder_name} | Progress: {folder_count}/{CHUNK_LIMIT} ---")
            
            tasks_list = []
            for i in range(batch_size):
                machine_unique_index = local_total + folder_count + i
                template_name = random.choice(templates_list)
                tasks_list.append((machine_unique_index, template_name, images_path, annotations_path))
                
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
            
            chunk_size = (len(tasks_list) + WORKERS - 1) // WORKERS
            task_chunks = [tasks_list[i:i + chunk_size] for i in range(0, len(tasks_list), chunk_size)]
            
            print(f"Generating {len(tasks_list)} samples with {WORKERS} workers...")
            pbar = tqdm(total=len(tasks_list), desc="Batch Generation")
            
            results = []
            for chunk in task_chunks:
                results.append(pool.apply_async(worker_process, args=(chunk, queue, books_pool)))
                
            for _ in range(len(tasks_list)):
                queue.get()
                pbar.update(1)
                
                # Atomic State Persistence immediately after every single sample generation
                state["current_folder_count"] += 1
                save_state(state)
                total_generated_this_run += 1
                
            # Ensure the batch completes
            for r in results:
                r.get()
                
            pbar.close()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
