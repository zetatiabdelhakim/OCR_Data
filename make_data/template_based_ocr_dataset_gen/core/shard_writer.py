"""
core/shard_writer.py
====================
Packs a completed chunk of loose (image, annotation) pairs into a single
WebDataset-style ``.tar`` shard, and unpacks one back to loose files.

Why tar at all
--------------
A 9990-sample chunk is ~40,000 loose files averaging ~100 KB. On the Hub the
per-file cost (xet hash, a ``.lock`` + ``.metadata`` sidecar written by
``upload_large_folder``, a preupload entry, a slot in a commit) dominates the
actual bytes, and the client-side API throttle caps the run at a few requests
per second. Packing the same chunk into one ~1.2 GB tar turns 40,000 files
into 1, which is where the upload speed comes from. It also makes the
post-upload verification affordable: comparing a handful of tar sizes against
the Hub is two API calls, whereas verifying 40,000 loose files was never
going to be practical — and that missing verification is exactly what let
truncated chunks ship and then get deleted locally.

Layout inside a shard follows the WebDataset convention: files that share a
basename are one sample, so ``datasets`` exposes the image as an ``image``
column and the JSON as a ``json`` column with no extra configuration.

    Zetati_home_001.tar
      sample_0000000.png
      sample_0000000.json
      sample_0000001.png
      sample_0000001.json
      ...

Atomicity
---------
Shards are written to ``<name>.tar.part`` and only renamed into place once
fully flushed and fsynced. ``upload_large_folder`` scans the outbox directory
for whatever is there, so it must never be able to observe a half-written
tar.
"""

from __future__ import annotations

import os
import tarfile

# Extensions the render engine and the augmentation pipeline can emit.
IMAGE_EXTS = (".png", ".jpg", ".jpeg")


def _stem_index(images_dir, exts=IMAGE_EXTS):
    """Map sample stem -> image filename for every image in a directory."""
    out = {}
    try:
        with os.scandir(images_dir) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                stem, ext = os.path.splitext(entry.name)
                if ext.lower() in exts:
                    out[stem] = entry.name
    except FileNotFoundError:
        pass
    return out


def _json_index(annotations_dir):
    """Set of sample stems that have an annotation on disk."""
    out = set()
    try:
        with os.scandir(annotations_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith(".json"):
                    out.add(entry.name[: -len(".json")])
    except FileNotFoundError:
        pass
    return out


def verify_pairs(images_dir, annotations_dir):
    """Check that every image has an annotation and vice versa.

    Returns ``(ok, missing_images, missing_jsons)`` where the two lists hold
    sample stems. Callers must refuse to pack a shard when ``ok`` is False —
    the published dataset previously accumulated thousands of annotations
    whose image had silently failed to be written, and nothing noticed.
    """
    images = _stem_index(images_dir)
    jsons = _json_index(annotations_dir)

    missing_images = sorted(jsons - set(images))
    missing_jsons = sorted(set(images) - jsons)
    return (not missing_images and not missing_jsons), missing_images, missing_jsons


def pack_shard(images_dir, annotations_dir, out_tar_path):
    """Pack every complete (image, annotation) pair into one tar shard.

    Only pairs are written: an image without its JSON (or the reverse) is
    skipped rather than producing a half sample in the dataset. Call
    :func:`verify_pairs` first if you want that to be an error instead.

    Returns ``(n_samples, size_bytes)``. Writes nothing and returns
    ``(0, 0)`` when there is no complete pair to pack.
    """
    images = _stem_index(images_dir)
    jsons = _json_index(annotations_dir)
    stems = sorted(set(images) & jsons)
    if not stems:
        return 0, 0

    os.makedirs(os.path.dirname(os.path.abspath(out_tar_path)), exist_ok=True)
    part_path = out_tar_path + ".part"

    # Uncompressed: PNG/JPEG payloads are already compressed, so gzip would
    # burn CPU for nothing and would also stop the Hub from serving byte
    # ranges out of the shard.
    with open(part_path, "wb") as raw:
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for stem in stems:
                img_name = images[stem]
                # Sorting by stem keeps a sample's members adjacent, which is
                # what WebDataset readers expect when grouping by key.
                tar.add(os.path.join(images_dir, img_name), arcname=img_name)
                tar.add(os.path.join(annotations_dir, stem + ".json"), arcname=stem + ".json")
        raw.flush()
        os.fsync(raw.fileno())

    os.replace(part_path, out_tar_path)
    return len(stems), os.path.getsize(out_tar_path)


def unpack_shard(tar_path, dest_dir, images_subdir="images", annotations_subdir="annotations"):
    """Expand a shard back into loose ``images/`` + ``annotations/`` folders.

    The escape hatch from the tar format — nothing in the dataset is locked
    away by the packing step.

    Returns ``(n_images, n_annotations)``.
    """
    images_dir = os.path.join(dest_dir, images_subdir)
    annotations_dir = os.path.join(dest_dir, annotations_subdir)
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(annotations_dir, exist_ok=True)

    n_images = n_annotations = 0
    with tarfile.open(tar_path, mode="r:*") as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = os.path.basename(member.name)
            ext = os.path.splitext(name)[1].lower()
            if ext == ".json":
                target_dir, n_annotations = annotations_dir, n_annotations + 1
            elif ext in IMAGE_EXTS:
                target_dir, n_images = images_dir, n_images + 1
            else:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, open(os.path.join(target_dir, name), "wb") as handle:
                while True:
                    block = source.read(1 << 20)
                    if not block:
                        break
                    handle.write(block)

    return n_images, n_annotations
