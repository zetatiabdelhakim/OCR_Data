"""
core/publisher.py
=================
Everything between "a chunk is finished" and "it is safely on the Hub".

Design
------
The outbox on disk *is* the repo layout::

    work/outbox/data/<user>_001.tar
    work/outbox/data_aug/<user>_001_aug1.tar
    work/outbox/.cache/huggingface/       <- upload_large_folder resume records

so publishing is a single ``upload_large_folder(folder_path=outbox)`` call with
no ``path_in_repo``, no staging root, no ``allow_patterns`` and no file moves.
(``upload_large_folder`` genuinely has no ``path_in_repo`` parameter — that is
why the previous implementation moved whole folders into a ``_hf_stage_*``
tree before uploading. Making the on-disk layout match the repo removes the
need for the move, and with it two silent data-loss paths: a hard kill during
staging orphaned the moved files where nothing would ever look for them again,
and an originals-succeeded/augs-failed run left the aug folder unrecoverable.)

Keeping ``.cache/huggingface`` inside the pushed directory also means a failed
push resumes on the next run instead of re-hashing and re-uploading from zero.

The verification gate
---------------------
``upload_large_folder`` swallows per-file failures and returns normally. The
previous code took that return as proof of success and deleted the local copy,
which is how the old dataset ended up with chunks whose annotations were all
present and whose images were absent. :func:`verify_pushed` re-reads the repo
and refuses to let anything be deleted until every shard is on the Hub at the
exact byte size it has locally. With tar shards that is two API calls per
push instead of the hundreds of thousands it would have cost per loose file —
the packing change is what makes the safety check affordable.
"""

from __future__ import annotations

import os
import shutil
import threading
import time

OUTBOX_NAME = "outbox"
PUSHING_PREFIX = "outbox_pushing_"


# ----------------------------------------------------------------------
# Outbox accounting
# ----------------------------------------------------------------------

def iter_shards(outbox_dir):
    """Yield ``(abs_path, path_in_repo)`` for every shard in an outbox.

    ``.cache`` is skipped: it holds upload_large_folder's resume metadata,
    which is uploaded to nothing and must not be verified against the repo.
    """
    for root, dirs, files in os.walk(outbox_dir):
        dirs[:] = [d for d in dirs if d != ".cache"]
        for name in files:
            if not name.endswith(".tar"):
                continue
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, outbox_dir).replace(os.sep, "/")
            yield abs_path, rel


def outbox_bytes(outbox_dir):
    """Total size of the shards waiting to be pushed."""
    total = 0
    for abs_path, _rel in iter_shards(outbox_dir):
        try:
            total += os.path.getsize(abs_path)
        except OSError:
            pass
    return total


def should_push(outbox_dir, threshold_gb):
    """True once the outbox has accumulated at least ``threshold_gb``."""
    if threshold_gb <= 0:
        return outbox_bytes(outbox_dir) > 0
    return outbox_bytes(outbox_dir) >= threshold_gb * (1024 ** 3)


def swap_outbox(work_dir):
    """Atomically set the current outbox aside for pushing.

    Renames ``outbox/`` to ``outbox_pushing_<n>/`` and recreates an empty
    ``outbox/``. The rename is what lets generation keep writing new shards
    while an upload is in flight — without it, a shard landing mid-scan could
    be picked up half-written or missed entirely.

    Returns the pushing directory, or None when the outbox held no shards.
    """
    outbox = os.path.join(work_dir, OUTBOX_NAME)
    if not os.path.isdir(outbox) or not any(True for _ in iter_shards(outbox)):
        return None

    n = 1
    while True:
        candidate = os.path.join(work_dir, f"{PUSHING_PREFIX}{n:03d}")
        if not os.path.exists(candidate):
            break
        n += 1

    os.rename(outbox, candidate)
    os.makedirs(outbox, exist_ok=True)
    return candidate


def pending_pushes(work_dir):
    """Pushing directories left behind by an interrupted run, oldest first."""
    try:
        entries = sorted(
            d for d in os.listdir(work_dir)
            if d.startswith(PUSHING_PREFIX) and os.path.isdir(os.path.join(work_dir, d))
        )
    except OSError:
        return []
    return [os.path.join(work_dir, d) for d in entries]


# ----------------------------------------------------------------------
# Progress
# ----------------------------------------------------------------------

class PushProgress:
    """Thread-safe snapshot of an in-flight push.

    The push may run in a background thread while the main thread owns the
    tqdm bar, so it cannot touch that bar directly. It writes here instead and
    whoever is idle and waiting polls it on a timer.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.label = None
        self.total_bytes = 0
        self.total_shards = 0
        self.started_at = None
        self.stage = "idle"

    def start(self, label, total_shards, total_bytes):
        with self._lock:
            self.label = label
            self.total_shards = total_shards
            self.total_bytes = total_bytes
            self.started_at = time.monotonic()
            self.stage = "uploading"

    def set_stage(self, stage):
        with self._lock:
            self.stage = stage

    def snapshot(self):
        with self._lock:
            return self.label, self.stage, self.total_shards, self.total_bytes, self.started_at


# ----------------------------------------------------------------------
# Repo helpers
# ----------------------------------------------------------------------

def _remote_shard_sizes(api, repo_id, root):
    """``{path_in_repo: size_bytes}`` for the .tar files directly under root."""
    from huggingface_hub import RepoFolder

    sizes = {}
    try:
        # Materialise inside the try: list_repo_tree is a generator, so a 404
        # for a root that does not exist yet is raised on iteration, not here.
        # Letting that escape would turn "the push did not land" into a crash
        # instead of a verification failure.
        tree = list(api.list_repo_tree(
            repo_id=repo_id, repo_type="dataset", path_in_repo=root, recursive=False
        ))
    except Exception:
        return sizes

    for item in tree:
        if isinstance(item, RepoFolder) or not item.path.endswith(".tar"):
            continue
        size = getattr(item, "size", None)
        lfs = getattr(item, "lfs", None)
        if lfs is not None and getattr(lfs, "size", None):
            # For LFS/xet-tracked files `size` can report the pointer's size;
            # lfs.size is the real payload.
            size = lfs.size
        sizes[item.path] = size
    return sizes


def verify_pushed(api, repo_id, pushing_dir):
    """Confirm every local shard is on the Hub at the same byte size.

    Returns ``(ok, problems)`` where problems is a list of human-readable
    strings. This is the gate that must pass before any local copy is
    deleted.
    """
    local = {}
    for abs_path, rel in iter_shards(pushing_dir):
        try:
            local[rel] = os.path.getsize(abs_path)
        except OSError as e:
            return False, [f"{rel}: cannot stat local shard ({e})"]

    if not local:
        return True, []

    roots = sorted({rel.split("/", 1)[0] for rel in local})
    remote = {}
    for root in roots:
        remote.update(_remote_shard_sizes(api, repo_id, root))

    problems = []
    for rel, size in sorted(local.items()):
        if rel not in remote:
            problems.append(f"{rel}: MISSING on the Hub")
        elif remote[rel] != size:
            problems.append(f"{rel}: size mismatch (local {size}, hub {remote[rel]})")

    return not problems, problems


def push_and_verify(api, repo_id, pushing_dir, num_workers, retry_attempts,
                    retry_backoff_seconds, progress=None, log=print):
    """Upload one pushing directory and verify it landed intact.

    Deletes ``pushing_dir`` only after verification passes. On failure the
    directory is left exactly where it is; the next run picks it up via
    :func:`pending_pushes` and resumes using the ``.cache/huggingface``
    records inside it.

    Returns True on a verified push.
    """
    shards = list(iter_shards(pushing_dir))
    if not shards:
        shutil.rmtree(pushing_dir, ignore_errors=True)
        return True

    total_bytes = sum(os.path.getsize(p) for p, _ in shards)
    label = os.path.basename(pushing_dir)
    log(f"Pushing {label}: {len(shards)} shard(s), {total_bytes / 1024**3:.2f} GB")
    if progress is not None:
        progress.start(label, len(shards), total_bytes)

    for attempt in range(1, retry_attempts + 1):
        try:
            api.upload_large_folder(
                repo_id=repo_id,
                repo_type="dataset",
                folder_path=pushing_dir,
                num_workers=num_workers,
                # Raw stdout would corrupt the live tqdm bar; progress is
                # reported through PushProgress instead.
                print_report=False,
            )
        except Exception as e:
            if attempt < retry_attempts:
                wait = retry_backoff_seconds * (2 ** (attempt - 1))
                log(f"  [push] {label} upload failed (attempt {attempt}/{retry_attempts}): {e} "
                    f"— retrying in {wait:.0f}s (resumes from .cache/huggingface)")
                time.sleep(wait)
                continue
            log(f"  [push] {label} upload failed after {retry_attempts} attempts: {e} "
                f"— left on disk, will resume next run.")
            return False

        if progress is not None:
            progress.set_stage("verifying")
        ok, problems = verify_pushed(api, repo_id, pushing_dir)
        if ok:
            log(f"{label} verified on the Hub ({len(shards)} shard(s)).")
            shutil.rmtree(pushing_dir, ignore_errors=True)
            return True

        # upload_large_folder returned success but the repo disagrees. Never
        # delete on this path — re-uploading is cheap because the resume
        # records mean only the missing shards move.
        log(f"  [push] {label} FAILED VERIFICATION — the Hub does not match local:")
        for problem in problems[:10]:
            log(f"           {problem}")
        if len(problems) > 10:
            log(f"           ... and {len(problems) - 10} more")
        if attempt < retry_attempts:
            wait = retry_backoff_seconds * (2 ** (attempt - 1))
            log(f"  [push] retrying {label} in {wait:.0f}s...")
            if progress is not None:
                progress.set_stage("uploading")
            time.sleep(wait)

    log(f"  [push] {label} could not be verified after {retry_attempts} attempts — "
        f"kept on disk at {pushing_dir}, nothing deleted. Re-run to retry.")
    return False


# ----------------------------------------------------------------------
# Local destination (destination: lcl)
# ----------------------------------------------------------------------

def move_to_local(pushing_dir, local_output_dir, log=print):
    """'lcl' destination: move shards into the local output tree."""
    moved = 0
    for abs_path, rel in iter_shards(pushing_dir):
        dest = os.path.join(local_output_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            os.remove(dest)
        shutil.move(abs_path, dest)
        moved += 1
    shutil.rmtree(pushing_dir, ignore_errors=True)
    log(f"Moved {moved} shard(s) to {local_output_dir}")
    return True


# ----------------------------------------------------------------------
# Dataset card
# ----------------------------------------------------------------------

DATASET_CARD = """---
pretty_name: {repo_name}
task_categories:
- image-to-text
language:
- ar
tags:
- ocr
- arabic
- synthetic
- webdataset
---

# {repo_name}

Synthetic Arabic document images with layout annotations, for OCR training.

## Layout

WebDataset `.tar` shards. Files sharing a basename are one sample, so the
image becomes the `image` column and the annotation the `json` column.

```
data/<contributor>_<NNN>.tar            originals (PNG + JSON)
data_aug/<contributor>_<NNN>_aug<K>.tar augmented variants (JPEG/PNG + JSON)
```

Each shard holds up to {chunk_limit} samples (~1.2 GB). `data/` and `data_aug/`
are separate so you can train on clean originals alone.

## Loading

```python
from datasets import load_dataset

# one shard
ds = load_dataset("webdataset",
                  data_files="hf://datasets/{repo_id}/data/<contributor>_001.tar",
                  split="train", streaming=True)

# a range of shards
ds = load_dataset("webdataset",
                  data_files="hf://datasets/{repo_id}/data/<contributor>_{{001..010}}.tar",
                  split="train", streaming=True)

# everything, originals + augmented
ds = load_dataset("webdataset", data_files={{"train": [
        "hf://datasets/{repo_id}/data/*.tar",
        "hf://datasets/{repo_id}/data_aug/*.tar"]}},
      split="train", streaming=True)
```

To get loose files back, use `unpack_shard.py` from the generator repo.

## Annotation schema

```json
{{
  "dimensions": {{"width": 0, "height": 0}},
  "blocks":  [{{"type": "...", "text": "...", "top_left_x": 0, "top_left_y": 0,
                "bottom_right_x": 0, "bottom_right_y": 0, "reading_index": 0}}],
  "images":  [{{"top_left_x": 0, "...": 0}}],
  "meta":    {{"template": "...", "hybrid": null, "page_font": "...",
               "language": "ar", "script": "arabic", "direction": "rtl",
               "augmentation": null}}
}}
```

`meta.augmentation` is `null` for originals and
`{{"name": ..., "params": {{...}}}}` for augmented variants.
"""


def ensure_dataset_card(api, repo_id, chunk_limit, private=True, log=print):
    """Create the repo if needed and make sure it has a card and LFS rules.

    `private` only applies at creation — an existing repo keeps its current
    visibility.
    """
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)

    try:
        existing = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    except Exception:
        existing = []

    if "README.md" not in existing:
        card = DATASET_CARD.format(
            repo_id=repo_id,
            repo_name=repo_id.split("/", 1)[-1],
            chunk_limit=chunk_limit,
        )
        api.upload_file(
            path_or_fileobj=card.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message="Add dataset card",
        )
        log("Uploaded dataset card.")

    if ".gitattributes" not in existing:
        # Datasets repos ship a default .gitattributes that already covers
        # *.tar; only write one when the repo has none at all.
        api.upload_file(
            path_or_fileobj=b"*.tar filter=lfs diff=lfs merge=lfs -text\n",
            path_in_repo=".gitattributes",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message="Track shards with LFS",
        )
