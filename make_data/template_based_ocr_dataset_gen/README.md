# Unified Arabic OCR Layout Generator

One generator, many document "genres" - A4 reports, business cards, book
covers, receipts, letters, minimalist posters, invoices, ID cards, and
dense math-proof pages - all producing the **same** PNG + JSON annotation
format your downstream OCR pipeline already expects.

## Why this exists

The previous setup was 5 separate scripts (`script.py`,
`script_charts_focus.py`, `script_equation_focus.py`,
`script_image_focus.py`, `script_text_focus.py`), each hard-coded to one
A4 content style. This replaces all five with:

- one shared rendering engine (`core/`)
- a **template per document genre** (`templates/`), each declaring its
  own real-world canvas size
- a single launcher (`generate.py`) that picks a template **uniformly at
  random** each sample - no fixed weighting table, so the mix feels
  organic rather than bucketed
- occasional **hybrid injection**: a `hybrid_probability` share of samples
  also get a random foreign snippet (a chart, an equation, a quote, a
  mini-table, a figure, or a theorem box) dropped into whatever template
  was picked - a chart inside a receipt, an equation on a book cover, etc.
- **Data augmentation & Hugging Face integration**: augmented variants of
  every image, packed into WebDataset shards and pushed to the Hub.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium --with-deps
```

We use:
- a streamed Arabic text corpus from the Hub (`text_corpus_hf_id`)
- `../nature_images/` - photos used for figures, galleries, book-cover art
- `../fonts/` - the Arabic font collection

Then set `user_name` and `repo_id` in `config.yaml` and run:

```bash
python generate.py
```

## Output format

Samples are packed into **WebDataset `.tar` shards**. Files sharing a
basename are one sample, so `datasets` exposes the image as an `image`
column and the annotation as a `json` column with no extra setup.

```
data/<user>_<NNN>.tar               originals   (PNG + JSON), ~1.2 GB
data_aug/<user>_<NNN>_aug<K>.tar    variant K   (JPEG + JSON), ~1.1 GB
```

Each shard holds up to `chunk_limit` samples. `data/` and `data_aug/` are
separate trees so you can train on clean originals alone.

Reading it back:

```python
from datasets import load_dataset

# one shard
ds = load_dataset("webdataset",
                  data_files="hf://datasets/<repo>/data/<user>_001.tar",
                  split="train", streaming=True)

# a range of shards
ds = load_dataset("webdataset",
                  data_files="hf://datasets/<repo>/data/<user>_{001..010}.tar",
                  split="train", streaming=True)

# everything, originals + augmented
ds = load_dataset("webdataset", data_files={"train": [
        "hf://datasets/<repo>/data/*.tar",
        "hf://datasets/<repo>/data_aug/*.tar"]},
      split="train", streaming=True)
```

To get loose PNG/JSON files back from a shard:

```bash
python unpack_shard.py path/to/<user>_001.tar --out ./unpacked
```

## How a run flows

```
work/current/            loose PNG/JSON pairs for the chunk being generated
   | chunk hits chunk_limit -> augment, drop incomplete pairs, pack
   v
work/outbox/             .tar shards, laid out exactly like the repo
   | outbox hits push_threshold_gb -> atomic rename
   v
work/outbox_pushing_N/   uploaded, VERIFIED against the Hub, then deleted
```

**Nothing local is deleted until the Hub has been re-read and confirmed to
hold every shard at its exact byte size.** `upload_large_folder()` swallows
per-file failures and returns normally, so a push that reports success is
not evidence the data arrived - the verification step is what makes it
safe to delete. A push that fails verification leaves its batch on disk;
re-running picks it up and resumes from the `.cache/huggingface` records
inside it.

Kill the process at any point (Ctrl+C, crash, reboot) and just re-run.

### Config knobs

Everything lives in `config.yaml`. The ones that matter most:

| Key | What |
|---|---|
| `num_samples` | max **originals** per run. Total images = `num_samples × (1 + augmentations_per_image)` |
| `chunk_limit` | originals per shard (9990 ≈ 1.2 GB) |
| `push_threshold_gb` | how much to accumulate before pushing. **Needs ~2× this free on disk** |
| `pipeline_upload` | keep generating during a push; set false to halve the disk requirement |
| `augmentations_per_image` | variants per original, each a different transform |
| `hybrid_probability` | chance (0-1) a sample gets a foreign snippet injected |
| `default_jitter_pct` | +/- size jitter applied to every canvas |
| `default_dpi` | mm → px conversion rate for real-world sizes |

## The 13 templates

| Template | Real-world basis | Notes |
|---|---|---|
| `a4_report` | A4, 210×297mm | headings/paragraphs/tables/figures grid (the original `script.py`) |
| `a4_charts` | A4 | magazine-style paragraphs + Chart.js statistical charts |
| `a4_paper` | A4 | title/abstract/sections/theorem boxes/equations, CSS multi-column |
| `a4_image_gallery` | A4 | photo galleries, floating-image paragraphs |
| `a4_literary` | A4 | narrative paragraphs, quotes, poetry blocks |
| `business_card` | 85×55mm (20% chance portrait) | logo + name/role/contact lines |
| `book_cover` | paperback/A5/mass-market/textbook presets | full-bleed art, title, author, tagline |
| `receipt` | 58mm or 80mm thermal width | **auto-height** - grows to fit however many item lines it gets, no dead space |
| `letter` | mostly A4, occasionally A5 memo | letterhead, date, salutation, body, closing, signature |
| `minimalist` | square / portrait poster / landscape banner | logo above centered title, lots of white space |
| `math_proof` | A4 dense page OR a small auto-height "notebook excerpt" (random) | standalone theorem boxes/equations, no paper wrapper |
| `id_card` | 90×55mm | photo placeholder, name, ID number, barcode |
| `invoice` | A4 | header, bill-to, itemized table, totals |

Every canvas size gets independent +/-12% jitter on width and height, so
even within one genre you get real size variety.

## Conventions every template follows (`core/render_engine.py`)

- Any leaf **text** node: `class="layout-node autofit-text" data-label="..."`
  → gets auto-shrunk word-by-word if it overflows its box, then its
  trimmed text is extracted into the JSON.
- Any leaf **visual** (image, chart canvas, logo, barcode):
  `class="layout-node" data-label="..." data-no-text="true"` → gets a
  bounding box but no text extraction.
- Any pure **wrapper**: `class="layout-node" data-label="..."` with no
  `autofit-text`/`data-no-text` → auto-detected as a parent (because it
  contains other `.layout-node` elements) and excluded from text
  extraction; still gets `reading_index: -1` in the JSON like before.
- Flow-style documents (letter, invoice, a4_paper, math_proof) wrap
  their stacked blocks in `id="content-flow"`. This enables automatic
  removal of any block that overflows the page bounds.

  **Why this matters / a gotcha worth knowing:** when `content-flow` has
  a definite height (not auto) and more content than fits, CSS spawns
  extra off-screen columns to hold the overflow. Headless Chromium has a
  real bug where the mere presence of those far-off-screen columns can
  blank out the **entire page's paint**, including perfectly in-bounds
  content. The crop step strips anything outside *all four* edges
  (not just right/bottom) specifically to eliminate those columns before
  the screenshot is taken. If you add a new flow-style template, keep
  this in mind - don't loosen that crop step.

## JSON schema

```json
{
  "dimensions": {"width": 0, "height": 0},
  "blocks":  [{"type": "text", "text": "...", "top_left_x": 0, "top_left_y": 0,
               "bottom_right_x": 0, "bottom_right_y": 0, "reading_index": 0}],
  "images":  [{"top_left_x": 0, "top_left_y": 0,
               "bottom_right_x": 0, "bottom_right_y": 0}],
  "tables": [], "markdown": "...", "header": null, "footer": null,
  "meta": {"template": "receipt", "hybrid": "chart",
           "page_font": "...", "title_font": "...",
           "language": "ar", "script": "arabic", "direction": "rtl",
           "augmentation": null}
}
```

`meta.augmentation` is `null` on originals and
`{"name": ..., "params": {...}}` on augmented variants, with every applied
parameter recorded so you can filter or reproduce a transform exactly.
Rotation is the only augmentation that changes dimensions, and it rewrites
every bounding box to match.

Annotations are written with compact separators and no indentation - they
are ~20% of the dataset's bytes, and pretty-printing them was inflating
each one by roughly half for no benefit.

## Adding a new template

1. Create `templates/my_new_thing.py` with a `NAME = "my_new_thing"` and
   a `generate(hybrid_html="") -> dict` returning
   `{"width": int, "height": int, "body": "<html>", "auto_height": bool}`.
2. Follow the `layout-node` / `autofit-text` / `data-no-text` conventions
   above so extraction works for free.
3. If it's a flow-style doc, wrap blocks in `id="content-flow"`.
4. If you want it to accept hybrid injections, place `hybrid_html`
   (already-wrapped via `core.hybrid.wrap_hybrid_block`) somewhere
   sensible in your body when it's non-empty.
5. Register it in `templates/__init__.py`. `generate.py` needs no
   changes - the new template is immediately in the random pool.

## A note on external resources

Every page loads Google Fonts, KaTeX and Chart.js from their public
CDNs. Run this somewhere with normal internet access - if those
requests are blocked (e.g. a locked-down sandbox/CI runner), math
equations and charts will silently render empty (the KaTeX call is
wrapped in a try/catch so a blocked CDN degrades gracefully instead of
crashing a whole generation run), but everything else still renders
correctly.
