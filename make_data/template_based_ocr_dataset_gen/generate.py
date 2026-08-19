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

Progress is checkpointed in state.yaml after every small batch of samples,
at every chunk boundary, and on shutdown. The script can be killed at any
point (Ctrl+C, crash, reboot, upload failure) and simply re-run — it will
reconcile against whatever is actually on disk / already pushed and resume
from exactly there, with no manual cleanup.
"""

import os

# Must be set before huggingface_hub is imported anywhere (it's read once at
# module-import time by huggingface_hub.constants) — raises hf_xet's transfer
# concurrency for faster pushes. setdefault() so an explicitly-set shell/env
# value always wins.
os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")

import json
import random
import asyncio
import multiprocessing
import threading
import signal
import time
import yaml
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


from core.text_provider import DocumentContext, current_document
from core import assets
from core.render_engine import build_html_page, render_and_extract
from core.hybrid import maybe_pick_hybrid
from core import augmentation
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

HYBRID_PROBABILITY = config.get("hybrid_probability", 0.10)
REFRESH_INTERVAL = config.get("refresh_interval", 1000)
NUM_BOOKS_TO_FETCH = config.get("num_books_to_fetch", 7)
TEXT_CORPUS_HF_ID = config.get("text_corpus_hf_id", "MathematicianNLPer/hamela_books_text_full_ok")
LOCAL_OUTPUT_DIR = config.get("local_output_dir", "./dataset_local_output")

ENABLE_AUGMENTATION = config.get("enable_augmentation", True)
AUGMENTATIONS_PER_IMAGE = config.get("augmentations_per_image", 3)

GLOBAL_COUNT_CHECK_INTERVAL = max(1, int(config.get("global_count_check_interval", 5)))
PIPELINE_UPLOAD = bool(config.get("pipeline_upload", True))
STATE_SAVE_INTERVAL = max(1, int(config.get("state_save_interval", 25)))
PROGRESS_REPORT_BATCH_SIZE = max(1, int(config.get("progress_report_batch_size", 25)))
UPLOAD_RETRY_ATTEMPTS = max(1, int(config.get("upload_retry_attempts", 4)))
UPLOAD_RETRY_BACKOFF_SECONDS = float(config.get("upload_retry_backoff_seconds", 10))
UPLOAD_PROGRESS_BATCHES = max(1, int(config.get("upload_progress_batches", 20)))

STATE_FILE = "state.yaml"

DEFAULT_STATE = {
    "current_folder_name": "",
    "current_folder_count": 0,
    "local_total_pushed": 0,
    "current_folder_index": 1,
    "last_global_count": 0,
    "flushes_since_global_check": 0,
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        state = dict(DEFAULT_STATE)
        state.update(loaded)
        return state
    return dict(DEFAULT_STATE)


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
            meta={
                "template": template_name,
                "hybrid": hybrid_name,
                # Resolve opaque CustomFont_N keys to real font filenames for the JSON record
                "page_font":  assets.FONT_NAME_MAP.get(doc_ctx.body_font,  doc_ctx.body_font),
                "title_font": assets.FONT_NAME_MAP.get(doc_ctx.title_font, doc_ctx.title_font),
                "language":   "ar",
                "script":     "arabic",
                "direction":  "rtl",
                "augmentation": None,  # originals always null; augmented overrides in augmentation.py
            },
        )
    finally:
        current_document.reset(token)


async def worker_task(tasks, queue, books_pool, report_batch_size):
    """Runs in a worker subprocess. Never prints directly (except the one
    catastrophic pre-work path below) — all diagnostics are sent back through
    the queue so the main process's progress bars stay uncorrupted."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:
            print(f"FATAL: Browser launch failed: {e}")
            for _ in tasks:
                queue.put({"results": [False], "errors": []})
            return

        tasks_done = 0
        batch_results = []
        batch_errors = []

        def flush_batch():
            nonlocal batch_results, batch_errors
            if batch_results:
                queue.put({"results": batch_results, "errors": batch_errors})
                batch_results = []
                batch_errors = []

        try:
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
                    batch_results.append(True)
                except Exception as e:
                    batch_results.append(False)
                    batch_errors.append((index, str(e)))
                    if "Connection closed" in str(e) or "Target closed" in str(e):
                        try:
                            await browser.close()
                        except Exception:
                            pass
                        try:
                            browser = await p.chromium.launch(headless=True)
                        except Exception as relaunch_err:
                            batch_errors.append((index, f"browser relaunch failed, worker giving up: {relaunch_err}"))
                            flush_batch()
                            remaining = len(tasks) - (i + 1)
                            if remaining > 0:
                                queue.put({"results": [False] * remaining, "errors": []})
                            tasks_done = len(tasks)
                            return
                tasks_done += 1
                if len(batch_results) >= report_batch_size:
                    flush_batch()
        except Exception as e:
            batch_errors.append((-1, f"worker crashed: {e}"))
        finally:
            flush_batch()
            remaining = len(tasks) - tasks_done
            if remaining > 0:
                queue.put({"results": [False] * remaining, "errors": []})
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass


def worker_process(tasks, queue, books_pool, report_batch_size):
    try:
        asyncio.run(worker_task(tasks, queue, books_pool, report_batch_size))
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(worker_task(tasks, queue, books_pool, report_batch_size))


def init_worker():
    # Only load heavy assets once per worker process!
    assets.load_assets()


def generate_folder_name(index):
    return f"{USER_NAME}_{index:03d}"


# ------------------------------------------------------------------
# Fast, scalable global-count tracking (Problem 1)
#
# A folder is only ever uploaded once it holds exactly CHUNK_LIMIT samples
# (see the main loop below), so every folder except possibly the newest one
# per contributor prefix is guaranteed to be full. Shallow-listing just the
# folder names under data/ (O(#folders)) and only exact-counting the newest
# folder per prefix is thousands of times cheaper than listing every file in
# the dataset, and gets relatively cheaper as the dataset grows.
# ------------------------------------------------------------------

def _shallow_list_folder_names(api, path_in_repo):
    from huggingface_hub import RepoFolder
    tree = api.list_repo_tree(repo_id=REPO_ID, repo_type="dataset", path_in_repo=path_in_repo, recursive=False)
    return [item.path.rsplit("/", 1)[-1] for item in tree if isinstance(item, RepoFolder)]


def _shallow_count_json_files(api, path_in_repo):
    from huggingface_hub import RepoFolder
    tree = api.list_repo_tree(repo_id=REPO_ID, repo_type="dataset", path_in_repo=path_in_repo, recursive=False)
    return sum(1 for item in tree if not isinstance(item, RepoFolder) and item.path.endswith(".json"))


def compute_global_count(api):
    """Team-wide count of ORIGINAL samples. Returns None on failure (e.g. repo
    doesn't exist yet) so callers can fall back to the last cached value."""
    try:
        folder_names = _shallow_list_folder_names(api, "data")
    except Exception as e:
        tqdm.write(f"Global count check failed (repo may not exist yet): {e}")
        return None

    if not folder_names:
        return 0

    by_prefix = {}
    for name in folder_names:
        prefix, sep, _idx = name.rpartition("_")
        if not sep:
            prefix = name
        by_prefix.setdefault(prefix, []).append(name)

    total = 0
    for _prefix, names in by_prefix.items():
        names.sort()
        total += (len(names) - 1) * CHUNK_LIMIT
        newest = names[-1]
        try:
            total += _shallow_count_json_files(api, f"data/{newest}")
        except Exception:
            total += CHUNK_LIMIT  # optimistic fallback — don't let one folder abort the whole check

    return total


def refresh_global_count(state, api, state_lock, force=False):
    """Refresh & cache the team-wide count, respecting GLOBAL_COUNT_CHECK_INTERVAL
    so a soft, team-wide budget doesn't need a network round-trip every flush."""
    if DESTINATION != "hf" or api is None:
        return 0

    with state_lock:
        pending = state.get("flushes_since_global_check", 0)
        cached = state.get("last_global_count", 0)

    if not force and pending < GLOBAL_COUNT_CHECK_INTERVAL:
        with state_lock:
            state["flushes_since_global_check"] = pending + 1
        return cached

    count = compute_global_count(api)
    if count is None:
        with state_lock:
            state["flushes_since_global_check"] = pending + 1
        return cached

    with state_lock:
        state["last_global_count"] = count
        state["flushes_since_global_check"] = 0
        save_state(state)
    return count


# ------------------------------------------------------------------
# Upload / move with retries (Problem 2, Problem 4B)
# ------------------------------------------------------------------

def _retry(fn, label):
    last_exc = None
    for attempt in range(1, UPLOAD_RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < UPLOAD_RETRY_ATTEMPTS:
                wait = UPLOAD_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                tqdm.write(f"  [upload] {label} failed (attempt {attempt}/{UPLOAD_RETRY_ATTEMPTS}): {e} "
                           f"— retrying in {wait:.0f}s...")
                time.sleep(wait)
    tqdm.write(f"  [upload] {label} failed after {UPLOAD_RETRY_ATTEMPTS} attempts: {last_exc}")
    raise last_exc


def _list_folder_files(local_path):
    """Relative paths of every file under local_path (used to split an
    upload into batches — this is what makes upload progress observable)."""
    try:
        return sorted(
            os.path.relpath(os.path.join(root, f), local_path)
            for root, _dirs, files in os.walk(local_path) for f in files
        )
    except OSError:
        return []


def _plan_batches(files):
    """Split a file list into UPLOAD_PROGRESS_BATCHES roughly-equal chunks."""
    if not files:
        return []
    batch_count = max(1, min(UPLOAD_PROGRESS_BATCHES, len(files)))
    batch_size = max(1, -(-len(files) // batch_count))  # ceil division
    return [files[i:i + batch_size] for i in range(0, len(files), batch_size)]


def _plan_job(kind, local_path, path_in_repo):
    """Precompute how many progress ticks this job (folder) will produce, so
    the caller can show a real X/Y over the whole chunk before starting."""
    if DESTINATION == "hf":
        batches = _plan_batches(_list_folder_files(local_path))
        return (kind, local_path, path_in_repo, batches, max(1, len(batches)))
    return (kind, local_path, path_in_repo, None, 1)


def _push_one_folder(api, kind, local_path, path_in_repo, batches, on_batch_done=None):
    """Upload (hf, retried, in several smaller batches so progress is
    actually observable instead of one opaque multi-GB call) or move (lcl)
    a single folder. Returns True/False."""
    if DESTINATION == "hf":
        if not batches:
            # Nothing to upload (shouldn't normally happen — jobs are only
            # queued for folders that hold generated files) — still tick
            # once so the aggregate counter this folder was promised in
            # _plan_job() (max(1, ...)) actually reaches its total.
            if on_batch_done is not None:
                on_batch_done()
            return True
        for i, batch in enumerate(batches, 1):
            def _do(batch=batch):
                api.upload_folder(
                    folder_path=local_path, path_in_repo=path_in_repo,
                    repo_id=REPO_ID, repo_type="dataset", allow_patterns=batch,
                )
            try:
                _retry(_do, label=f"{kind} ({path_in_repo}) batch {i}/{len(batches)}")
            except Exception:
                return False
            if on_batch_done is not None:
                on_batch_done()
        shutil.rmtree(local_path, ignore_errors=True)
        return True
    else:
        dest_path = os.path.join(LOCAL_OUTPUT_DIR, *path_in_repo.split("/"))
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.move(local_path, dest_path)
            if on_batch_done is not None:
                on_batch_done()
            return True
        except Exception as e:
            tqdm.write(f"  [move] {kind} ({path_in_repo}) failed: {e}")
            return False


class UploadProgress:
    """Thread-safe progress snapshot for an in-flight upload_chunk() call.

    upload_chunk() may run in a background thread while the main thread is
    busy showing generation progress on the shared bar — it can't safely
    touch that bar directly. Instead it writes here, and whoever is actually
    idle and waiting (wait_for_pending_upload(), below) polls this on a timer
    so the bar keeps visibly ticking (batches pushed + elapsed time) instead
    of sitting frozen on a single static message for however long the
    transfer of one large folder takes.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.folder_name = None
        self.done = 0
        self.total = 0
        self.started_at = None

    def start(self, folder_name, total):
        with self._lock:
            self.folder_name = folder_name
            self.done = 0
            self.total = total
            self.started_at = time.monotonic()

    def tick(self):
        with self._lock:
            self.done += 1

    def snapshot(self):
        with self._lock:
            return self.folder_name, self.done, self.total, self.started_at


def upload_chunk(folder_name, folder_count, state, api, state_lock, stop_event, pbar=None, progress=None):
    """Push one completed chunk's originals + augmented folders. This is the
    slow, I/O-bound part — safe to run in a background thread (Problem 2A),
    and pushes the 4 folders concurrently rather than sequentially (2B)."""
    jobs = []
    originals_dir = os.path.abspath(f"./temp_generation_{folder_name}")
    if os.path.isdir(originals_dir):
        jobs.append(("originals", originals_dir, f"data/{folder_name}"))

    if ENABLE_AUGMENTATION:
        for aug_i in range(1, AUGMENTATIONS_PER_IMAGE + 1):
            aug_folder_name = f"{folder_name}_aug{aug_i}"
            aug_dir = os.path.abspath(f"./temp_generation_{aug_folder_name}")
            if os.path.isdir(aug_dir):
                jobs.append((f"aug{aug_i}", aug_dir, f"data_aug/{aug_folder_name}"))

    if not jobs:
        return True

    # Plan real, verifiable progress ticks up front: each folder's upload is
    # split into several smaller batches (each a genuine, completed
    # upload_folder() call), so the counter below actually advances
    # continuously through a multi-GB folder instead of sitting on "0/4"
    # for however long a single opaque call takes.
    job_plans = [_plan_job(kind, path, repo_path) for kind, path, repo_path in jobs]
    total_ticks = sum(n for *_, n in job_plans)

    tqdm.write(f"Pushing chunk '{folder_name}' ({folder_count} samples, {len(jobs)} folder(s), "
               f"{total_ticks} batch(es))...")
    if pbar is not None:
        pbar.set_postfix_str(f"uploading {folder_name}: 0/{total_ticks}", refresh=True)
    if progress is not None:
        progress.start(folder_name, total_ticks)

    done_lock = threading.Lock()
    ticks_done = 0

    def _on_batch_done():
        nonlocal ticks_done
        with done_lock:
            ticks_done += 1
            n = ticks_done
        if pbar is not None:
            pbar.set_postfix_str(f"uploading {folder_name}: {n}/{total_ticks}", refresh=True)
        if progress is not None:
            progress.tick()

    results = {}
    with ThreadPoolExecutor(max_workers=len(job_plans)) as ex:
        futures = {
            ex.submit(_push_one_folder, api, kind, path, repo_path, batches, _on_batch_done): kind
            for kind, path, repo_path, batches, _n in job_plans
        }
        for fut in as_completed(futures):
            kind = futures[fut]
            results[kind] = fut.result()

    if not results.get("originals", False):
        tqdm.write(f"Chunk '{folder_name}': originals failed to push after retries — left on disk at "
                   f"{originals_dir}, will be pushed automatically next run.")
        stop_event.set()
        return False

    failed_augs = [k for k, ok in results.items() if k != "originals" and not ok]
    if failed_augs:
        tqdm.write(f"Chunk '{folder_name}': augmented folder(s) {failed_augs} failed after retries — "
                   f"left on disk, will be pushed automatically next run.")

    tqdm.write(f"Chunk '{folder_name}' push complete.")

    refresh_global_count(state, api, state_lock)
    if DESTINATION == "hf":
        with state_lock:
            current_global = state.get("last_global_count", 0)
        if current_global >= GLOBAL_LIMIT:
            tqdm.write(f"Global limit reached! ({current_global} >= {GLOBAL_LIMIT}). Stopping new work.")
            stop_event.set()

    return True


def rotate_to_next_folder(state, state_lock):
    """Snapshot the just-completed folder and immediately assign the next
    one, so the caller can start generating the next chunk right away
    without waiting for this one's upload."""
    with state_lock:
        old_name = state["current_folder_name"]
        old_count = state["current_folder_count"]

        state["local_total_pushed"] = state.get("local_total_pushed", 0) + old_count
        state["current_folder_index"] = state.get("current_folder_index", 1) + 1
        state["current_folder_name"] = generate_folder_name(state["current_folder_index"])
        state["current_folder_count"] = 0
        save_state(state)

    return old_name, old_count


def recover_orphaned_chunks(state, api, state_lock, stop_event, pbar=None):
    """Find leftover temp_generation_* folders from a previous run that were
    never successfully pushed (process killed mid-upload, or an upload
    permanently failed after retries) and push them before starting new
    work. Makes resume correct across restarts regardless of where a prior
    run was interrupted."""
    current = state.get("current_folder_name", "")
    try:
        entries = [d for d in os.listdir(".") if os.path.isdir(d) and d.startswith("temp_generation_")]
    except OSError:
        return

    bases = set()
    for d in entries:
        name = d[len("temp_generation_"):]
        for suf in ("_aug1", "_aug2", "_aug3"):
            if name.endswith(suf):
                name = name[: -len(suf)]
                break
        bases.add(name)
    bases.discard(current)

    for folder_name in sorted(bases):
        images_dir = os.path.join(f"./temp_generation_{folder_name}", "images")
        if not os.path.isdir(images_dir):
            continue
        count = len([f for f in os.listdir(images_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))])
        if count == 0:
            continue
        tqdm.write(f"Found un-pushed leftover chunk '{folder_name}' ({count} samples) from a previous run "
                   f"— pushing it first...")
        upload_chunk(folder_name, count, state, api, state_lock, stop_event, pbar=pbar)
        if stop_event.is_set():
            break


# ------------------------------------------------------------------
# Augmentation catch-up (idempotent — safe to call every loop iteration)
#
# Ensures every original currently in a folder has all its augmented
# variants written, regardless of whether they were produced just now or are
# left over from an interrupted previous run. This is what makes resume
# correct even if the process was killed mid-augmentation, where a naive
# "only augment this round's new samples" approach would otherwise let a
# folder reach CHUNK_LIMIT and get flushed with missing augmented data.
# ------------------------------------------------------------------

def catch_up_augmentation(folder_name, images_path, annotations_path, pool, pbar=None):
    if not ENABLE_AUGMENTATION:
        return

    aug_dirs = {}
    for aug_i in range(1, AUGMENTATIONS_PER_IMAGE + 1):
        aug_dir = os.path.abspath(f"./temp_generation_{folder_name}_aug{aug_i}")
        os.makedirs(os.path.join(aug_dir, "images"), exist_ok=True)
        os.makedirs(os.path.join(aug_dir, "annotations"), exist_ok=True)
        aug_dirs[aug_i] = aug_dir

    if not os.path.isdir(images_path):
        return

    originals = sorted(f for f in os.listdir(images_path) if f.endswith(".png"))

    pending = []
    for img_file in originals:
        json_file = img_file.replace(".png", ".json")
        img_src = os.path.join(images_path, img_file)
        json_src = os.path.join(annotations_path, json_file)
        if not os.path.exists(json_src):
            continue

        missing_slots = []
        already_used = set()
        for aug_i in range(1, AUGMENTATIONS_PER_IMAGE + 1):
            aug_dir = aug_dirs[aug_i]
            existing_img = (
                os.path.exists(os.path.join(aug_dir, "images", img_file))
                or os.path.exists(os.path.join(aug_dir, "images", os.path.splitext(img_file)[0] + ".jpg"))
            )
            if not existing_img:
                missing_slots.append(aug_i)
                continue
            existing_json = os.path.join(aug_dir, "annotations", json_file)
            try:
                with open(existing_json, "r", encoding="utf-8") as jf:
                    name = json.load(jf).get("meta", {}).get("augmentation", {}).get("name")
                if name:
                    already_used.add(name)
            except Exception:
                pass

        if not missing_slots:
            continue

        weights = None
        if already_used:
            weights = dict(augmentation.AUGMENTATION_WEIGHTS)
            for name in already_used:
                weights[name] = 0.0

        aug_names = augmentation.pick_n_distinct(len(missing_slots), weights=weights)
        for aug_i, aug_name in zip(missing_slots, aug_names):
            aug_dir = aug_dirs[aug_i]
            aug_img_path = os.path.join(aug_dir, "images", img_file)
            aug_json_path = os.path.join(aug_dir, "annotations", json_file)
            pending.append((img_src, json_src, aug_img_path, aug_json_path, aug_name))

    if not pending:
        return

    tqdm.write(f"Augmenting {folder_name}: {len(pending)} outstanding (image, variant) pair(s)...")
    if pbar is not None:
        pbar.set_postfix_str(f"augmenting {folder_name}: 0/{len(pending)}", refresh=True)

    async_results = [pool.apply_async(augmentation.augment_sample, args=task) for task in pending]
    done = 0
    for ar in async_results:
        try:
            success, err = ar.get(timeout=60)
            if not success and err:
                tqdm.write(f"  [aug] {err}")
        except Exception as e:
            tqdm.write(f"  [aug] task failed: {e}")
        done += 1
        if pbar is not None:
            pbar.set_postfix_str(f"augmenting {folder_name}: {done}/{len(pending)}", refresh=True)


def main():
    from dotenv import load_dotenv
    from datasets import load_dataset
    from huggingface_hub import login, HfApi
    import queue as queue_module
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

    state = load_state()
    state_lock = threading.Lock()
    stop_event = threading.Event()
    shutdown_requested = threading.Event()

    def _handle_signal(signum, frame):
        if shutdown_requested.is_set():
            tqdm.write("\nForce exit.")
            os._exit(1)
        shutdown_requested.set()
        tqdm.write("\nShutdown requested — finishing in-flight work and saving state "
                   "(press Ctrl+C again to force-exit)...")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if not state.get("current_folder_name"):
        with state_lock:
            state["current_folder_index"] = state.get("current_folder_index", 1)
            state["current_folder_name"] = generate_folder_name(state["current_folder_index"])
            state["current_folder_count"] = 0
            save_state(state)

    # Created early (before recovery/dataset-init/env-checks) so every one of
    # those startup phases — including pushing a leftover chunk from a killed
    # prior run, which can itself take a long time — shows up on it too,
    # instead of the terminal going silent until real generation starts.
    pbar = tqdm(total=NUM_SAMPLES, desc="Overall progress", leave=True)

    # Push anything left over from a previous run before doing anything else.
    recover_orphaned_chunks(state, api, state_lock, stop_event, pbar=pbar)

    if DESTINATION == "hf" and not stop_event.is_set():
        global_count = refresh_global_count(state, api, state_lock, force=True)
        if global_count >= GLOBAL_LIMIT:
            tqdm.write(f"Global limit of {GLOBAL_LIMIT} reached ({global_count}). Exiting.")
            pbar.close()
            return

    if stop_event.is_set():
        tqdm.write("Stopped during startup recovery — see messages above. Safe to re-run.")
        pbar.close()
        return

    pbar.set_postfix_str("initializing dataset stream", refresh=True)
    try:
        # Randomize the seed so every execution gets completely different books
        ds = load_dataset(TEXT_CORPUS_HF_ID, split="train", streaming=True, token=hf_token)
        ds = ds.shuffle(buffer_size=1000, seed=random.randint(0, 1000000))
        dataset_iterator = iter(ds)
    except Exception as e:
        tqdm.write(f"Error loading dataset, using fallback text: {e}")
        dataset_iterator = None

    templates_list = list(TEMPLATES)
    manager = multiprocessing.Manager()
    queue = manager.Queue()

    total_generated_this_run = 0

    pbar.set_postfix_str("running environment checks", refresh=True)
    try:
        import psutil
        available_gb = psutil.virtual_memory().available / (1024**3)
        global WORKERS
        if available_gb < 2.0:
            tqdm.write(f"WARNING: Only {available_gb:.1f}GB RAM available. Reducing workers.")
            WORKERS = min(WORKERS, max(2, int(available_gb)))
    except ImportError:
        pass

    pbar.set_postfix_str("checking browser", refresh=True)

    async def smoke_test():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
    try:
        asyncio.run(smoke_test())
    except Exception as e:
        tqdm.write(f"FATAL: Playwright smoke test failed: {e}. Please run 'playwright install chromium'")
        pbar.close()
        return

    # A single bar, updated in place — separate stacked bars need multi-line
    # ANSI cursor control that not every terminal handles reliably, which
    # shows up as a new line being printed on every update instead of the
    # line refreshing. One bar's plain carriage-return update works
    # everywhere. Current-phase detail (generating/augmenting/uploading)
    # goes in the postfix text on that same line instead of a second bar.
    pbar.set_postfix_str("starting", refresh=True)

    pending_upload_thread = None
    pending_upload_name = None
    pending_upload_progress = None
    dirty_samples = 0
    augmented_upto_cache = {}

    def wait_for_pending_upload():
        nonlocal pending_upload_thread, pending_upload_name, pending_upload_progress
        if pending_upload_thread is not None:
            # Poll instead of a single blocking join() so the bar keeps
            # visibly ticking (folder count + elapsed seconds) for however
            # long the transfer takes, instead of freezing on one message.
            while pending_upload_thread.is_alive():
                folder, done, total, started_at = pending_upload_progress.snapshot()
                elapsed = f"{time.monotonic() - started_at:.0f}s" if started_at else "0s"
                pbar.set_postfix_str(
                    f"waiting for upload of {pending_upload_name} to finish "
                    f"({done}/{total} folder(s) pushed, {elapsed} elapsed)",
                    refresh=True,
                )
                pending_upload_thread.join(timeout=1.0)
            pending_upload_thread = None
            pending_upload_name = None
            pending_upload_progress = None

    with multiprocessing.Pool(processes=WORKERS, initializer=init_worker) as pool:
        while (
            total_generated_this_run < NUM_SAMPLES
            and not stop_event.is_set()
            and not shutdown_requested.is_set()
        ):
            with state_lock:
                folder_name = state["current_folder_name"]
                folder_count = state["current_folder_count"]

            temp_dir = os.path.abspath(f"./temp_generation_{folder_name}")
            images_path = os.path.join(temp_dir, "images")
            annotations_path = os.path.join(temp_dir, "annotations")

            os.makedirs(images_path, exist_ok=True)
            os.makedirs(annotations_path, exist_ok=True)

            # Reconcile in-memory state with actual files on disk. Self-heals
            # after a crash — bounded by CHUNK_LIMIT, not total dataset size.
            actual_pairs = len([
                f for f in os.listdir(images_path) if f.endswith('.png')
                and os.path.exists(os.path.join(annotations_path, f.replace('.png', '.json')))
            ])
            if actual_pairs != folder_count:
                tqdm.write(f"State correction: state said {folder_count}, actual valid pairs = {actual_pairs}")
                with state_lock:
                    state["current_folder_count"] = actual_pairs
                    save_state(state)
                folder_count = actual_pairs

            # Catch up any outstanding augmentation for this folder before
            # deciding whether it's ready to flush — cheap no-op once caught up.
            if augmented_upto_cache.get(folder_name) != folder_count:
                catch_up_augmentation(folder_name, images_path, annotations_path, pool, pbar)
                augmented_upto_cache[folder_name] = folder_count

            if folder_count >= CHUNK_LIMIT:
                old_name, old_count = rotate_to_next_folder(state, state_lock)
                wait_for_pending_upload()  # at most one outstanding upload at a time
                if stop_event.is_set():
                    break
                if PIPELINE_UPLOAD:
                    pending_upload_name = old_name
                    pending_upload_progress = UploadProgress()
                    pending_upload_thread = threading.Thread(
                        target=upload_chunk,
                        args=(old_name, old_count, state, api, state_lock, stop_event, None, pending_upload_progress),
                        daemon=False,
                    )
                    pending_upload_thread.start()
                else:
                    upload_chunk(old_name, old_count, state, api, state_lock, stop_event, pbar)
                continue

            with state_lock:
                local_total = state["local_total_pushed"]
            user_historical_total = local_total + folder_count
            if user_historical_total >= USER_LOCAL_LIMIT:
                tqdm.write(f"User local limit of {USER_LOCAL_LIMIT} reached "
                           f"(Historical Total: {user_historical_total}). Exiting.")
                break

            remaining_in_chunk = CHUNK_LIMIT - folder_count
            remaining_in_run = NUM_SAMPLES - total_generated_this_run
            remaining_allowed = USER_LOCAL_LIMIT - user_historical_total
            batch_size = min(remaining_in_chunk, remaining_in_run, REFRESH_INTERVAL, remaining_allowed)

            if batch_size <= 0:
                break

            tqdm.write(f"--- Folder: {folder_name} | Progress: {folder_count}/{CHUNK_LIMIT} ---")

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

            gen_done = 0
            pbar.set_postfix_str(f"generating {folder_name}: {gen_done}/{len(tasks_list)}", refresh=True)

            results = []
            for chunk in task_chunks:
                results.append(pool.apply_async(worker_process, args=(chunk, queue, books_pool, PROGRESS_REPORT_BATCH_SIZE)))

            completed = 0
            while completed < len(tasks_list):
                try:
                    payload = queue.get(timeout=120)
                except queue_module.Empty:
                    tqdm.write("WARNING: Worker timeout — some workers may have died.")
                    break

                for err_index, err_msg in payload.get("errors", []):
                    tqdm.write(f"  [gen] sample {err_index}: {err_msg}")

                for success in payload.get("results", []):
                    completed += 1
                    gen_done += 1
                    pbar.set_postfix_str(f"generating {folder_name}: {gen_done}/{len(tasks_list)}", refresh=False)
                    pbar.update(1)
                    if success:
                        with state_lock:
                            state["current_folder_count"] += 1
                            dirty_samples += 1
                            if dirty_samples >= STATE_SAVE_INTERVAL:
                                save_state(state)
                                dirty_samples = 0
                    total_generated_this_run += 1

            for r in results:
                r.get()

            # Always persist at the end of a batch — batches are already
            # infrequent (one per chunk in the common configuration).
            with state_lock:
                save_state(state)
                dirty_samples = 0

        # Final flush of any remaining generated (and now fully augmented)
        # samples in this run — still inside the pool's lifetime.
        wait_for_pending_upload()

        with state_lock:
            remaining_count = state.get("current_folder_count", 0)
            final_folder = state.get("current_folder_name", "")

        if remaining_count > 0 and not stop_event.is_set():
            temp_dir = os.path.abspath(f"./temp_generation_{final_folder}")
            images_path = os.path.join(temp_dir, "images")
            annotations_path = os.path.join(temp_dir, "annotations")
            if os.path.isdir(images_path):
                catch_up_augmentation(final_folder, images_path, annotations_path, pool, pbar)
            tqdm.write("Finalizing and pushing remaining samples...")
            old_name, old_count = rotate_to_next_folder(state, state_lock)
            upload_chunk(old_name, old_count, state, api, state_lock, stop_event, pbar)

    pbar.close()

    if shutdown_requested.is_set():
        print("\nShutdown complete — state saved, safe to resume with the same command.")
    elif stop_event.is_set():
        print("\nStopped (limit reached or a push failed permanently after retries) — state saved, safe to resume.")
    else:
        print("\nRun complete — state saved.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
