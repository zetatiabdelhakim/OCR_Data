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

Pipeline shape
--------------
    work/current/          loose PNG/JSON pairs for the chunk being generated
        |  chunk reaches chunk_limit -> augment, verify, pack
        v
    work/outbox/           .tar shards, laid out exactly like the repo
        |  outbox reaches push_threshold_gb -> atomic rename
        v
    work/outbox_pushing_N/ uploaded, then VERIFIED against the Hub, then deleted

Nothing is deleted locally until the Hub has been re-read and confirmed to
hold every shard at its exact byte size. Progress is checkpointed in
state.yaml after every small batch of samples, at every chunk boundary, and on
shutdown. The script can be killed at any point (Ctrl+C, crash, reboot, upload
failure) and simply re-run — it reconciles against whatever is actually on
disk and resumes from exactly there, with no manual cleanup.
"""

import os
import json
import random
import asyncio
import multiprocessing
import threading
import signal
import time
import yaml
import shutil
from tqdm import tqdm


from core.text_provider import DocumentContext, current_document
from core import assets
from core.render_engine import build_html_page, render_and_extract
from core.hybrid import maybe_pick_hybrid
from core import augmentation
from core import publisher
from core import shard_writer
from templates import TEMPLATES

# ------------------------------------------------------------------
# Load configuration
# ------------------------------------------------------------------
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

USER_NAME = config.get("user_name", "user")
REPO_ID = config.get("repo_id", "org/repo")
REPO_PRIVATE = bool(config.get("repo_private", True))
DESTINATION = config.get("destination", "lcl")
GLOBAL_LIMIT = config.get("global_limit", 50000)
USER_LOCAL_LIMIT = config.get("user_local_limit", 20000)
CHUNK_LIMIT = config.get("chunk_limit", 9000)
NUM_SAMPLES = config.get("num_samples", 2000)
UPLOAD_WORKERS = config.get("upload_workers", 8)

WORKERS = config.get("workers", "auto")
MAXIMUM_NUM_OF_WORKERS = config.get("maximum_num_of_workers", 10)
if WORKERS == "auto":
    WORKERS = min(os.cpu_count() or 4, MAXIMUM_NUM_OF_WORKERS)

HYBRID_PROBABILITY = config.get("hybrid_probability", 0.10)
REFRESH_INTERVAL = config.get("refresh_interval", 1000)
CORPUS_POOL_SIZE = max(1, int(config.get("corpus_pool_size", 3000)))
CORPUS_RANDOM_JUMP = max(0, int(config.get("corpus_random_jump", 20000)))
TEXT_CORPUS_HF_ID = config.get("text_corpus_hf_id", "MathematicianNLPer/hamela_books_text_full_ok")
LOCAL_OUTPUT_DIR = os.path.abspath(config.get("local_output_dir", "./dataset_local_output"))
WORK_DIR = os.path.abspath(config.get("work_dir", "./work"))

ENABLE_AUGMENTATION = config.get("enable_augmentation", True)
AUGMENTATIONS_PER_IMAGE = config.get("augmentations_per_image", 3)

GLOBAL_COUNT_CHECK_INTERVAL = max(1, int(config.get("global_count_check_interval", 5)))
PIPELINE_UPLOAD = bool(config.get("pipeline_upload", True))
STATE_SAVE_INTERVAL = max(1, int(config.get("state_save_interval", 25)))
PROGRESS_REPORT_BATCH_SIZE = max(1, int(config.get("progress_report_batch_size", 25)))
UPLOAD_RETRY_ATTEMPTS = max(1, int(config.get("upload_retry_attempts", 4)))
UPLOAD_RETRY_BACKOFF_SECONDS = float(config.get("upload_retry_backoff_seconds", 10))

PUSH_THRESHOLD_GB = float(config.get("push_threshold_gb", 50))
MIN_FREE_DISK_GB = float(config.get("min_free_disk_gb", 0))

# hf_xet's aggressive transfer mode. Must be set before huggingface_hub is
# imported anywhere (constants read it at module-import time). Off by default:
# see the config comment — it coincides with the first chunks that shipped
# with their annotations present and their images missing.
if bool(config.get("hf_xet_high_performance", False)):
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")

# Hub API quota (server side: 1000 requests / 5 min). The limiter stays
# deliberately below it and blocks (never errors) when the budget is spent.
HF_RATE_LIMIT_REQUESTS = int(config.get("hf_rate_limit_requests", 900))
HF_RATE_LIMIT_PERIOD = float(config.get("hf_rate_limit_period", 300))

STATE_FILE = "state.yaml"

CURRENT_DIR = os.path.join(WORK_DIR, "current")
OUTBOX_DIR = os.path.join(WORK_DIR, publisher.OUTBOX_NAME)

IMAGES_PATH = os.path.join(CURRENT_DIR, "images")
ANNOTATIONS_PATH = os.path.join(CURRENT_DIR, "annotations")
AUG_IMAGES_PATH = os.path.join(CURRENT_DIR, "images_aug")
AUG_ANNOTATIONS_PATH = os.path.join(CURRENT_DIR, "annotations_aug")

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


def free_disk_gb(path):
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except OSError:
        return float("inf")


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

                # captureScreenshot "Unable to capture screenshot" is a
                # transient Chromium glitch — retry the same sample a few
                # times with a fresh page/browser instead of losing the slot.
                succeeded = False
                last_err = None
                for attempt in range(1, 4):
                    try:
                        await generate_one(browser, index, books_pool, template_name, images_path, annotations_path)
                        succeeded = True
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 3:
                            await asyncio.sleep(1.0 * attempt)
                            try:
                                await browser.close()
                            except Exception:
                                pass
                            browser = await p.chromium.launch(headless=True)
                if succeeded:
                    batch_results.append(True)
                else:
                    e = last_err
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
# Global-count tracking
#
# A chunk is one .tar under data/, packed only when it holds CHUNK_LIMIT
# originals (the sole exception being a final partial chunk at the end of a
# run). So a single shallow listing of data/ gives the team-wide total, which
# is far cheaper than the per-folder recursion this needed when a chunk was
# 20,000 loose files. A trailing partial chunk makes the figure a slight
# over-estimate, which is fine for a soft, team-wide budget.
# ------------------------------------------------------------------

def compute_global_count(api):
    """Team-wide count of ORIGINAL samples. Returns None on failure (e.g. repo
    doesn't exist yet) so callers can fall back to the last cached value."""
    from huggingface_hub import RepoFolder
    try:
        # list_repo_tree returns a generator, so the HTTP call (and a 404 for a
        # data/ that does not exist yet) only happens on iteration — it has to
        # be materialised inside the try or the error escapes.
        tree = list(api.list_repo_tree(
            repo_id=REPO_ID, repo_type="dataset", path_in_repo="data", recursive=False
        ))
    except Exception as e:
        tqdm.write(f"Global count check skipped (no data/ in the repo yet): {e}")
        return None

    shards = [i for i in tree if not isinstance(i, RepoFolder) and i.path.endswith(".tar")]
    return len(shards) * CHUNK_LIMIT


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
# Packing a finished chunk into shards
# ------------------------------------------------------------------

def _drop_orphans(images_dir, annotations_dir, label):
    """Delete half-written pairs so they are regenerated rather than shipped.

    An image with no annotation is a crash between the two writes; an
    annotation with no image is a failed image write. Either way the sample is
    incomplete and must not reach a shard — the published dataset previously
    accumulated thousands of the latter.
    """
    ok, missing_images, missing_jsons = shard_writer.verify_pairs(images_dir, annotations_dir)
    if ok:
        return 0

    removed = 0
    for stem in missing_images:  # annotation without an image
        try:
            os.remove(os.path.join(annotations_dir, stem + ".json"))
            removed += 1
        except OSError:
            pass
    for stem in missing_jsons:  # image without an annotation
        for ext in shard_writer.IMAGE_EXTS:
            path = os.path.join(images_dir, stem + ext)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
                break

    tqdm.write(f"  [pack] {label}: dropped {removed} incomplete file(s) "
               f"({len(missing_images)} annotation(s) without an image, "
               f"{len(missing_jsons)} image(s) without an annotation)")
    return removed


def pack_current_chunk(folder_name, pbar=None):
    """Pack work/current into shards in work/outbox. Returns samples packed.

    Originals become data/<folder>.tar. Each augmentation slot becomes its own
    data_aug/<folder>_aug<K>.tar, which keeps the variant grouping the previous
    directory layout had and lets a consumer load, say, only the first variant.
    """
    if pbar is not None:
        pbar.set_postfix_str(f"packing {folder_name}", refresh=True)

    _drop_orphans(IMAGES_PATH, ANNOTATIONS_PATH, folder_name)
    n_samples, size = shard_writer.pack_shard(
        IMAGES_PATH, ANNOTATIONS_PATH, os.path.join(OUTBOX_DIR, "data", f"{folder_name}.tar")
    )
    if n_samples == 0:
        return 0
    total_bytes = size
    tqdm.write(f"  [pack] data/{folder_name}.tar: {n_samples} sample(s), {size / 1024**3:.2f} GB")

    if ENABLE_AUGMENTATION:
        _drop_orphans(AUG_IMAGES_PATH, AUG_ANNOTATIONS_PATH, f"{folder_name} (aug)")
        # Variants are named <stem>_NN; split them back out by slot so each
        # slot gets its own shard.
        by_slot = _split_aug_by_slot()
        for slot in sorted(by_slot):
            slot_images, slot_annotations = by_slot[slot]
            n_aug, aug_size = shard_writer.pack_shard(
                slot_images, slot_annotations,
                os.path.join(OUTBOX_DIR, "data_aug", f"{folder_name}_aug{slot}.tar"),
            )
            total_bytes += aug_size
            tqdm.write(f"  [pack] data_aug/{folder_name}_aug{slot}.tar: "
                       f"{n_aug} sample(s), {aug_size / 1024**3:.2f} GB")
        shutil.rmtree(os.path.join(CURRENT_DIR, "_slots"), ignore_errors=True)

    # The chunk is now inside immutable tars; the loose copies are redundant.
    shutil.rmtree(IMAGES_PATH, ignore_errors=True)
    shutil.rmtree(ANNOTATIONS_PATH, ignore_errors=True)
    shutil.rmtree(AUG_IMAGES_PATH, ignore_errors=True)
    shutil.rmtree(AUG_ANNOTATIONS_PATH, ignore_errors=True)

    tqdm.write(f"Chunk '{folder_name}' packed: {n_samples} sample(s), "
               f"{total_bytes / 1024**3:.2f} GB total.")
    return n_samples


def _split_aug_by_slot():
    """Group augmented variants by slot number, as one directory pair per slot.

    Variants are written flat as ``<stem>_NN.<ext>``, but pack_shard works on a
    (images_dir, annotations_dir) pair, so each slot needs its own view of the
    files. Hard links make that free — no second copy of several GB — and the
    whole scratch tree is deleted immediately after packing.

    Returns ``{slot: (images_dir, annotations_dir)}``.
    """
    slots_root = os.path.join(CURRENT_DIR, "_slots")
    shutil.rmtree(slots_root, ignore_errors=True)

    by_slot = {}
    for sub, source in (("images_aug", AUG_IMAGES_PATH), ("annotations_aug", AUG_ANNOTATIONS_PATH)):
        if not os.path.isdir(source):
            continue
        for fname in os.listdir(source):
            slot_text = os.path.splitext(fname)[0].rsplit("_", 1)[-1]
            if not slot_text.isdigit():
                continue
            slot = int(slot_text)

            by_slot.setdefault(slot, (
                os.path.join(slots_root, f"aug{slot}", "images_aug"),
                os.path.join(slots_root, f"aug{slot}", "annotations_aug"),
            ))

            slot_dir = os.path.join(slots_root, f"aug{slot}", sub)
            os.makedirs(slot_dir, exist_ok=True)
            src = os.path.join(source, fname)
            dst = os.path.join(slot_dir, fname)
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)  # different volume, or no link support

    return by_slot


# ------------------------------------------------------------------
# Pushing
# ------------------------------------------------------------------

def push_pending(api, pushing_dir, state, state_lock, stop_event, progress=None):
    """Push one pending directory and, if it lands, refresh the global count."""
    if DESTINATION == "hf":
        ok = publisher.push_and_verify(
            api, REPO_ID, pushing_dir,
            num_workers=UPLOAD_WORKERS,
            retry_attempts=UPLOAD_RETRY_ATTEMPTS,
            retry_backoff_seconds=UPLOAD_RETRY_BACKOFF_SECONDS,
            progress=progress,
            log=tqdm.write,
        )
    else:
        ok = publisher.move_to_local(pushing_dir, LOCAL_OUTPUT_DIR, log=tqdm.write)

    if not ok:
        # Leave the directory in place and stop taking on new work rather than
        # generating more data we may also fail to ship.
        stop_event.set()
        return False

    refresh_global_count(state, api, state_lock)
    if DESTINATION == "hf":
        with state_lock:
            current_global = state.get("last_global_count", 0)
        if current_global >= GLOBAL_LIMIT:
            tqdm.write(f"Global limit reached! ({current_global} >= {GLOBAL_LIMIT}). Stopping new work.")
            stop_event.set()
    return True


def rotate_to_next_folder(state, state_lock, packed_count):
    """Record a packed chunk and move on to the next folder name."""
    with state_lock:
        state["local_total_pushed"] = state.get("local_total_pushed", 0) + packed_count
        state["current_folder_index"] = state.get("current_folder_index", 1) + 1
        state["current_folder_name"] = generate_folder_name(state["current_folder_index"])
        state["current_folder_count"] = 0
        save_state(state)


# ------------------------------------------------------------------
# Augmentation catch-up (idempotent — safe to call every loop iteration)
#
# Ensures every original currently on disk has all its augmented variants
# written, regardless of whether they were produced just now or are left over
# from an interrupted previous run. This is what makes resume correct even if
# the process was killed mid-augmentation, where a naive "only augment this
# round's new samples" approach would let a chunk get packed with missing
# augmented data.
# ------------------------------------------------------------------

def catch_up_augmentation(folder_name, pool, pbar=None):
    if not ENABLE_AUGMENTATION:
        return

    os.makedirs(AUG_IMAGES_PATH, exist_ok=True)
    os.makedirs(AUG_ANNOTATIONS_PATH, exist_ok=True)

    if not os.path.isdir(IMAGES_PATH):
        return

    originals = sorted(f for f in os.listdir(IMAGES_PATH) if f.endswith(".png"))

    # Two directory listings instead of a stat per (original, slot) pair. This
    # runs once per refresh batch, so at chunk_limit 9990 x 3 variants the
    # naive version was ~60k stat calls a pass — expensive on Windows.
    existing_variants = {os.path.splitext(f)[0] for f in os.listdir(AUG_IMAGES_PATH)}
    existing_annotations = {os.path.splitext(f)[0] for f in os.listdir(AUG_ANNOTATIONS_PATH)}
    have_originals = {os.path.splitext(f)[0] for f in os.listdir(ANNOTATIONS_PATH)}

    pending = []
    for img_file in originals:
        stem = os.path.splitext(img_file)[0]
        img_src = os.path.join(IMAGES_PATH, img_file)
        json_src = os.path.join(ANNOTATIONS_PATH, stem + ".json")
        if stem not in have_originals:
            continue

        # An augmented variant exists if its suffixed image (or JPEG twin,
        # when AUGMENTATION_OUTPUT_FORMAT is jpeg) is on disk. Variants of
        # sample_0000001 are sample_0000001_01.._NN, zero-padded for stable
        # lexicographic ordering in the shard.
        missing_slots = []
        already_used = set()
        for aug_i in range(1, AUGMENTATIONS_PER_IMAGE + 1):
            variant = f"{stem}_{aug_i:02d}"
            # A slot counts as filled only when BOTH halves are on disk —
            # a variant image without its annotation (or vice versa) would be
            # dropped at pack time, so treat it as missing and redo it.
            if variant not in existing_variants or variant not in existing_annotations:
                missing_slots.append(aug_i)
                continue
            try:
                with open(os.path.join(AUG_ANNOTATIONS_PATH, variant + ".json"), "r", encoding="utf-8") as jf:
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
            aug_img_path = os.path.join(AUG_IMAGES_PATH, f"{stem}_{aug_i:02d}.png")
            aug_json_path = os.path.join(AUG_ANNOTATIONS_PATH, f"{stem}_{aug_i:02d}.json")
            pending.append((img_src, json_src, aug_img_path, aug_json_path, aug_name))

    if not pending:
        return

    tqdm.write(f"Augmenting {folder_name}: {len(pending)} outstanding (image, variant) pair(s)...")
    if pbar is not None:
        pbar.set_postfix_str(f"augmenting {folder_name}: 0/{len(pending)}", refresh=True)

    async_results = [pool.apply_async(augmentation.augment_sample, args=task) for task in pending]
    done = 0
    failures = 0
    for ar in async_results:
        try:
            success, err = ar.get(timeout=300)
            if not success:
                failures += 1
                if err:
                    tqdm.write(f"  [aug] {err}")
        except Exception as e:
            failures += 1
            tqdm.write(f"  [aug] task failed: {e}")
        done += 1
        if pbar is not None and done % 25 == 0:
            pbar.set_postfix_str(f"augmenting {folder_name}: {done}/{len(pending)}", refresh=True)

    if failures:
        tqdm.write(f"  [aug] {failures}/{len(pending)} variant(s) failed — they will be "
                   f"retried on the next pass, and any incomplete pair is dropped before packing.")


def main():
    from dotenv import load_dotenv
    from huggingface_hub import login, HfApi
    from core.hf_throttle import install as install_hf_throttle
    import queue as queue_module
    load_dotenv()

    # The corpus is a nice-to-have: there is already a fallback text path for
    # when the stream can't be reached. Importing `datasets` at the top of
    # main() meant an unimportable pyarrow (a broken wheel, or a Windows
    # Application Control policy blocking its DLLs) killed the whole run
    # instead of degrading to that fallback.
    try:
        from datasets import load_dataset
    except Exception as e:
        load_dataset = None
        print(f"WARNING: 'datasets' is unavailable ({e}).")
        print("         Falling back to placeholder text — samples will NOT be "
              "linguistically varied. Fix this before generating real data.")

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(OUTBOX_DIR, exist_ok=True)

    required_gb = MIN_FREE_DISK_GB
    available_disk = free_disk_gb(WORK_DIR)
    if required_gb > 0 and available_disk < required_gb:
        print(f"Error: only {available_disk:.1f} GB free at {WORK_DIR}, but min_free_disk_gb "
              f"is {required_gb:.0f}. With push_threshold_gb={PUSH_THRESHOLD_GB:.0f} and "
              f"pipeline_upload={PIPELINE_UPLOAD}, you need roughly "
              f"{2 * PUSH_THRESHOLD_GB + 5:.0f} GB. Lower push_threshold_gb, set "
              f"pipeline_upload: false, or free up space.")
        return

    hf_token = os.environ.get("HF_TOKEN")
    api = None
    if DESTINATION == "hf":
        if not hf_token:
            print("Error: HF_TOKEN is not set in .env. Required when destination is 'hf'.")
            return
        # Must be installed before the first hub API call (login included) —
        # patches huggingface_hub's shared session so every request from every
        # thread (upload workers included) shares one rate budget.
        install_hf_throttle(
            max_requests=HF_RATE_LIMIT_REQUESTS,
            period_seconds=HF_RATE_LIMIT_PERIOD,
        )
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
    # those startup phases — including pushing a batch left over from a killed
    # prior run, which can itself take a long time — shows up on it too,
    # instead of the terminal going silent until real generation starts.
    pbar = tqdm(total=NUM_SAMPLES, desc="Overall progress", leave=True)

    if DESTINATION == "hf":
        pbar.set_postfix_str("preparing repo", refresh=True)
        try:
            publisher.ensure_dataset_card(api, REPO_ID, CHUNK_LIMIT,
                                          private=REPO_PRIVATE, log=tqdm.write)
        except Exception as e:
            tqdm.write(f"Could not prepare repo metadata (continuing): {e}")

    # Finish anything a previous run left mid-push before starting new work.
    for pending_dir in publisher.pending_pushes(WORK_DIR):
        tqdm.write(f"Found un-pushed batch from a previous run: {os.path.basename(pending_dir)}")
        pbar.set_postfix_str(f"resuming push of {os.path.basename(pending_dir)}", refresh=True)
        push_pending(api, pending_dir, state, state_lock, stop_event)
        if stop_event.is_set():
            break

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

    # ------------------------------------------------------------------
    # Text corpus, fetched ONCE.
    #
    # .shuffle() was costing 4-5 minutes before the first sample rendered: on
    # a 24-shard streaming dataset it opens and interleaves every shard, and
    # yields nothing until that is done. Dropping it takes the open from
    # ~250s to ~10-50s.
    #
    # Randomness is preserved by jumping to a random row instead — redrawn
    # every run, so two machines never start in the same place. Once the
    # stream is open, reading more rows is essentially free, so the whole
    # pool is read here and the network is never touched for text again.
    # ------------------------------------------------------------------
    books_pool = []
    if load_dataset is not None:
        pbar.set_postfix_str("opening text corpus (one-time, ~10-60s)", refresh=True)
        try:
            ds = load_dataset(TEXT_CORPUS_HF_ID, split="train", streaming=True, token=hf_token)
            # Small on purpose: a jump of 250k rows measured at ~10 minutes,
            # 50k at ~11s. This is plenty to make runs diverge on a 4.6M-row
            # corpus, and the pool read below scatters further.
            jump = random.randint(0, CORPUS_RANDOM_JUMP)
            if jump:
                ds = ds.skip(jump)
            iterator = iter(ds)
            pbar.set_postfix_str(
                f"reading {CORPUS_POOL_SIZE} corpus pages from row ~{jump:,}", refresh=True)
            for _ in range(CORPUS_POOL_SIZE):
                item = next(iterator)
                books_pool.append(item.get("text", "") or "")
            books_pool = [b for b in books_pool if b.strip()]
        except StopIteration:
            books_pool = [b for b in books_pool if b.strip()]
        except Exception as e:
            tqdm.write(f"Error loading text corpus, using fallback text: {e}")

    if books_pool:
        tqdm.write(f"Text corpus ready: {len(books_pool)} pages "
                   f"({sum(len(b) for b in books_pool) / 1_000_000:.1f}M chars).")
    else:
        tqdm.write("WARNING: no text corpus — falling back to placeholder text. "
                   "Samples will NOT be linguistically varied.")
        books_pool = ["نص تجريبي افتراضي للاختبار فقط. هذا النص يظهر عند فشل الاتصال بقاعدة البيانات."]

    templates_list = list(TEMPLATES)
    # Shut down explicitly at the end of main(): the Manager runs its own
    # server process, and without a shutdown() it survives the parent and has
    # to be killed by hand.
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
    # everywhere. Current-phase detail (generating/augmenting/packing/pushing)
    # goes in the postfix text on that same line instead of a second bar.
    pbar.set_postfix_str("starting", refresh=True)

    pending_push_thread = None
    pending_push_progress = None
    dirty_samples = 0
    # num_samples counts successes, so a batch where every sample fails makes
    # no progress and would otherwise be retried forever. Bail out after a few
    # completely fruitless batches instead of spinning.
    empty_batches = 0
    MAX_EMPTY_BATCHES = 3

    def wait_for_pending_push():
        nonlocal pending_push_thread, pending_push_progress
        if pending_push_thread is None:
            return
        # Poll instead of a single blocking join() so the bar keeps visibly
        # ticking for however long the transfer takes, instead of freezing on
        # one message.
        while pending_push_thread.is_alive():
            label, stage, shards, total_bytes, started_at = pending_push_progress.snapshot()
            elapsed = f"{time.monotonic() - started_at:.0f}s" if started_at else "0s"
            pbar.set_postfix_str(
                f"{stage} {label}: {shards} shard(s), "
                f"{total_bytes / 1024**3:.1f} GB, {elapsed} elapsed",
                refresh=True,
            )
            pending_push_thread.join(timeout=1.0)
        pending_push_thread = None
        pending_push_progress = None

    def start_push(force=False):
        """Swap the outbox out and push it, if it is big enough (or forced)."""
        nonlocal pending_push_thread, pending_push_progress
        if not force and not publisher.should_push(OUTBOX_DIR, PUSH_THRESHOLD_GB):
            return
        # At most one push in flight: two would double the disk footprint and
        # blow past what min_free_disk_gb budgeted for.
        wait_for_pending_push()
        if stop_event.is_set():
            return
        pushing_dir = publisher.swap_outbox(WORK_DIR)
        if pushing_dir is None:
            return
        if PIPELINE_UPLOAD and not force:
            pending_push_progress = publisher.PushProgress()
            pending_push_thread = threading.Thread(
                target=push_pending,
                args=(api, pushing_dir, state, state_lock, stop_event, pending_push_progress),
                daemon=False,
            )
            pending_push_thread.start()
        else:
            push_pending(api, pushing_dir, state, state_lock, stop_event)

    with multiprocessing.Pool(processes=WORKERS, initializer=init_worker) as pool:
        while (
            total_generated_this_run < NUM_SAMPLES
            and not stop_event.is_set()
            and not shutdown_requested.is_set()
        ):
            with state_lock:
                folder_name = state["current_folder_name"]
                folder_count = state["current_folder_count"]

            os.makedirs(IMAGES_PATH, exist_ok=True)
            os.makedirs(ANNOTATIONS_PATH, exist_ok=True)

            # Reconcile in-memory state with actual files on disk. Self-heals
            # after a crash — bounded by CHUNK_LIMIT, not total dataset size.
            actual_pairs = len([
                f for f in os.listdir(IMAGES_PATH) if f.endswith('.png')
                and os.path.exists(os.path.join(ANNOTATIONS_PATH, f.replace('.png', '.json')))
            ])
            if actual_pairs != folder_count:
                tqdm.write(f"State correction: state said {folder_count}, actual valid pairs = {actual_pairs}")
                with state_lock:
                    state["current_folder_count"] = actual_pairs
                    save_state(state)
                folder_count = actual_pairs

            if folder_count >= CHUNK_LIMIT:
                catch_up_augmentation(folder_name, pool, pbar)
                packed = pack_current_chunk(folder_name, pbar)
                rotate_to_next_folder(state, state_lock, packed)
                start_push()
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

            if free_disk_gb(WORK_DIR) < 5:
                tqdm.write(f"Stopping: less than 5 GB free at {WORK_DIR}. "
                           f"Free up space (or lower push_threshold_gb) and re-run.")
                break

            tqdm.write(f"--- Folder: {folder_name} | Progress: {folder_count}/{CHUNK_LIMIT} ---")

            # folder_count only counts valid pairs; failed samples leave
            # permanent holes in the numbering, so local_total + folder_count
            # can point at indices that already exist (or below the current
            # max). Target the actual holes first, then extend past the max.
            existing_indices = set()
            for f in os.listdir(IMAGES_PATH):
                # Only a png WITH its json counts as occupying a slot — an
                # orphan png (crash between the two writes) must be regenerated.
                if f.startswith("sample_") and f.endswith(".png"):
                    if not os.path.exists(os.path.join(ANNOTATIONS_PATH, f[:-4] + ".json")):
                        continue
                    try:
                        existing_indices.add(int(f[len("sample_"):-len(".png")]))
                    except ValueError:
                        pass
            target_count = max(local_total + folder_count + batch_size, local_total + folder_count)
            wanted = set(range(local_total + folder_count, target_count)) - existing_indices
            next_new = (max(existing_indices) + 1) if existing_indices else (local_total + folder_count)
            while len(wanted) < batch_size:
                wanted.add(next_new)
                next_new += 1
            batch_indices = sorted(wanted)[:batch_size]

            tasks_list = []
            for machine_unique_index in batch_indices:
                template_name = random.choice(templates_list)
                tasks_list.append((machine_unique_index, template_name, IMAGES_PATH, ANNOTATIONS_PATH))

            chunk_size = (len(tasks_list) + WORKERS - 1) // WORKERS
            task_chunks = [tasks_list[i:i + chunk_size] for i in range(0, len(tasks_list), chunk_size)]

            # Each worker gets its own random draw from the pool rather than a
            # full copy: the pool is pickled to every worker on every batch, so
            # sending all of it N times would be the dominant IPC cost. Drawing
            # independently also means two workers rarely render the same page.
            per_worker = max(1, len(books_pool) // max(1, len(task_chunks)))
            worker_pools = [
                random.sample(books_pool, min(len(books_pool), per_worker))
                for _ in task_chunks
            ]

            gen_done = 0
            pbar.set_postfix_str(f"generating {folder_name}: {gen_done}/{len(tasks_list)}", refresh=True)

            results = []
            for chunk, chunk_books in zip(task_chunks, worker_pools):
                results.append(pool.apply_async(worker_process, args=(chunk, queue, chunk_books, PROGRESS_REPORT_BATCH_SIZE)))

            completed = 0
            timed_out = False
            succeeded_this_batch = 0
            while completed < len(tasks_list):
                try:
                    payload = queue.get(timeout=120)
                except queue_module.Empty:
                    tqdm.write("WARNING: Worker timeout — some workers may have died. "
                               "Their samples will be regenerated on the next pass.")
                    timed_out = True
                    break

                for err_index, err_msg in payload.get("errors", []):
                    tqdm.write(f"  [gen] sample {err_index}: {err_msg}")

                for success in payload.get("results", []):
                    completed += 1
                    gen_done += 1
                    pbar.set_postfix_str(f"generating {folder_name}: {gen_done}/{len(tasks_list)}", refresh=False)
                    pbar.update(1)
                    if success:
                        # Only successes count toward the run budget, so
                        # num_samples really is "max originals this run".
                        total_generated_this_run += 1
                        succeeded_this_batch += 1
                        with state_lock:
                            state["current_folder_count"] += 1
                            dirty_samples += 1
                            if dirty_samples >= STATE_SAVE_INTERVAL:
                                save_state(state)
                                dirty_samples = 0

            # A bounded wait: an un-bounded r.get() here would hang the whole
            # run forever on a worker that died without draining its tasks.
            # Whatever a dead worker failed to produce is picked up by the
            # on-disk reconciliation at the top of the next iteration.
            for r in results:
                try:
                    r.get(timeout=5 if timed_out else 300)
                except Exception as e:
                    tqdm.write(f"  [gen] worker batch did not finish cleanly: {e}")

            # Always persist at the end of a batch.
            with state_lock:
                save_state(state)
                dirty_samples = 0

            if succeeded_this_batch == 0:
                empty_batches += 1
                tqdm.write(f"WARNING: batch produced no usable samples "
                           f"({empty_batches}/{MAX_EMPTY_BATCHES} before giving up).")
                if empty_batches >= MAX_EMPTY_BATCHES:
                    tqdm.write("Stopping: generation is failing for every sample. "
                               "Check the [gen] errors above (browser, fonts, or corpus). "
                               "Whatever was already packed is still safe.")
                    break
            else:
                empty_batches = 0

            # Augment as we go rather than saving 3x the work for the chunk
            # boundary — this keeps the render/augment stall short and even.
            catch_up_augmentation(folder_name, pool, pbar)

        # Final flush of whatever this run produced, still inside the pool's
        # lifetime so augmentation can run.
        with state_lock:
            remaining_count = state.get("current_folder_count", 0)
            final_folder = state.get("current_folder_name", "")

        if remaining_count > 0 and not stop_event.is_set():
            tqdm.write("Finalizing remaining samples...")
            catch_up_augmentation(final_folder, pool, pbar)
            packed = pack_current_chunk(final_folder, pbar)
            if packed:
                rotate_to_next_folder(state, state_lock, packed)

    # Push everything still in the outbox, regardless of the byte threshold.
    # Skipped on Ctrl+C: the user asked to stop, and shards left in the outbox
    # are not lost — they join the next run's first push.
    if not stop_event.is_set() and not shutdown_requested.is_set():
        start_push(force=True)
    wait_for_pending_push()

    pbar.close()
    try:
        manager.shutdown()
    except Exception:
        pass

    leftover = publisher.pending_pushes(WORK_DIR)
    if leftover:
        print(f"\n{len(leftover)} batch(es) still pending on disk under {WORK_DIR} — "
              f"nothing was deleted. Re-run to retry the push.")
    waiting = publisher.outbox_bytes(OUTBOX_DIR)
    if waiting:
        print(f"{waiting / 1024**3:.2f} GB of packed shards are waiting in the outbox — "
              f"they will go out with the next push.")

    if shutdown_requested.is_set():
        print("\nShutdown complete — state saved, safe to resume with the same command.")
    elif stop_event.is_set():
        print("\nStopped (limit reached or a push failed verification) — state saved, safe to resume.")
    else:
        print("\nRun complete — state saved.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
