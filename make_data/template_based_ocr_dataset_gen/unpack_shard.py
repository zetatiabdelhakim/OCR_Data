"""
unpack_shard.py
===============
Expand one or more WebDataset shards back into loose ``images/`` +
``annotations/`` folders — the escape hatch from the tar format.

    python unpack_shard.py work/outbox/data/Zetati_home_001.tar --out ./unpacked
    python unpack_shard.py "dataset_local_output/data/*.tar" --out ./unpacked

A shard downloaded from the Hub works the same way:

    huggingface-cli download <repo> data/Zetati_home_001.tar \\
        --repo-type dataset --local-dir ./dl
    python unpack_shard.py ./dl/data/Zetati_home_001.tar --out ./unpacked
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

from core.shard_writer import unpack_shard


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("shards", nargs="+",
                        help="Shard .tar path(s); glob patterns are accepted.")
    parser.add_argument("--out", default="./unpacked",
                        help="Destination directory (default: ./unpacked)")
    parser.add_argument("--per-shard", action="store_true",
                        help="Unpack each shard into its own subdirectory of --out "
                             "instead of merging them all together.")
    args = parser.parse_args()

    paths = []
    for pattern in args.shards:
        matches = sorted(glob.glob(pattern))
        paths.extend(matches if matches else [pattern])

    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        for path in missing:
            print(f"error: no such shard: {path}", file=sys.stderr)
        return 1

    total_images = total_annotations = 0
    for path in paths:
        dest = args.out
        if args.per_shard:
            dest = os.path.join(args.out, os.path.splitext(os.path.basename(path))[0])
        n_images, n_annotations = unpack_shard(path, dest)
        total_images += n_images
        total_annotations += n_annotations
        flag = "" if n_images == n_annotations else "   <-- MISMATCH"
        print(f"{os.path.basename(path)}: {n_images} image(s), "
              f"{n_annotations} annotation(s) -> {dest}{flag}")

    print(f"\nTotal: {total_images} image(s), {total_annotations} annotation(s)")
    if total_images != total_annotations:
        print("warning: image and annotation counts differ — the shard is incomplete.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
