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
- occasional **hybrid injection**: ~28% of samples also get a random
  foreign snippet (a chart, an equation, a quote, a mini-table, a
  figure, or a theorem box) dropped into whatever template was picked -
  a chart inside a receipt, an equation on a book cover, etc.
- **Data Augmentation & Hugging Face Integration**: Includes data augmentation steps to make the dataset more robust, and natively connects to Hugging Face for seamless dataset uploading and sharing.

## Setup

```bash
pip install playwright tqdm nest_asyncio
playwright install chromium --with-deps
```

We use:
- `../shamela_1M_words.txt` - Our Arabic corpus (space-separated words)
- `nature_images/` - a folder of photos (used for figures, galleries,
  book-cover art)

Just run:

```bash
python generate.py
```

Output goes to `../dataset/images/sample_XXXXXXX.png` and
`../dataset/annotations/sample_XXXXXXX.json` (same convention as before).

### Config knobs

| Where | What |
|---|---|
| `generate.py` → `NUM_SAMPLES` | how many samples to generate |
| `generate.py` → `HYBRID_PROBABILITY` | chance (0-1) a sample gets a foreign snippet injected |
| `core/assets.py` → `DEFAULT_JITTER_PCT` | +/- size jitter applied to every canvas (default 12%, i.e. inside the requested 10-15% range) |
| `core/assets.py` → `DEFAULT_DPI` | mm → px conversion rate for real-world sizes |

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

## JSON schema (unchanged, plus two additive fields)

```json
{
  "boxes": [ {"label": "...", "text": "...", "x": .., "y": .., "width": .., "height": .., "bottom": .., "right": .., "reading_index": ..}, ... ],
  "canvas": {"width": .., "height": ..},
  "template": "receipt",
  "hybrid": "chart"
}
```

`boxes` is identical in shape to what the original scripts produced, so
existing downstream code keeps working. `canvas`/`template`/`hybrid` are
new, purely additive fields - useful for filtering/balancing the dataset
later, safe to ignore if you don't need them.

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
