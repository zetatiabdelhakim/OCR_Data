# Open Arabic Document-Layout Datasets & Randomized-Layout Data Generation

This repository brings together the Arabic document-layout resources used to train and evaluate our OCR / document-understanding models. It combines three established, third-party benchmarks with a home-grown synthetic generation pipeline (`make_data/`) that produces fully-Arabic, randomly-laid-out page images with pixel-accurate bounding-box ground truth — heading, paragraph, table, and figure blocks, in dozens of fonts and colors.

## 📁 Repository structure

```
.
├── BCE-Arabic-v1/                  # Public DLA benchmark (scanned book pages)
├── SDADDS-Guelma_Handwritten/      # Synthetic degraded handwritten Arabic pages
├── SDADDS-Guelma_Printed/          # Synthetic degraded printed Arabic pages
├── ahmedheakl.ipynb                # Loads the BCE-layout split from Hugging Face
└── make_data/                      # Our own synthetic layout generator
    ├── scrape_arabic.py
    ├── scrape_images.py
    ├── script.py
    ├── visual.ipynb
    └── dataset/
        ├── images/
        └── annotations/
```

---

## 1. `BCE-Arabic-v1/`

A published Arabic Document Layout Analysis (DLA) benchmark, originally introduced by Saad et al. (2016), built from 1,833 scanned pages drawn from 180 books to cover a wide range of real Arabic page layouts — multi-column text, tables, embedded photos, and mixed typefaces. This folder holds a working subset of roughly 1,200 sample page images used here for layout-detection experiments. It also ships a small notebook that lets you pick a target block type (heading / paragraph / table / figure) and a sample image, then renders that sample's ground-truth bounding boxes on top for a quick visual check.

<p align="center">
  <img src="BCE-Arabic v1\multi-columns\d-0.jpg" alt="BCE-Arabic-v1 sample page" width="420"><br>
</p>

## 2. `SDADDS-Guelma_Handwritten/`

The handwritten half of **SDADDS-Guelma** (Synthetic Degraded Arabic Document Data Set), created by Dr. Abderrahmane Kefali's team at the University of Guelma. Real handwritten Arabic page images are synthetically degraded and composited over a variety of paper textures and historical backgrounds (stains, folds, faded ink, uneven lighting) to mimic real archival wear. Each generated image ships with ground truth at the text-line, word, and connected-component level. The handwritten and printed halves together scale into the millions of synthetic samples in the dataset's full release.

🔗 **[Download SDADDS-Guelma](https://zenodo.org/records/10896124)** — official dataset page (Zenodo).

<p align="center">
  <img src="SDADDS-Guelma_Handwritten\Degraded_IMG\Comb+Curvature\HW1Uni_BG1-CU.jpg" alt="SDADDS-Guelma handwritten sample" width="420"><br>
</p>

## 3. `SDADDS-Guelma_Printed/`

The printed-text counterpart of the same SDADDS-Guelma pipeline: clean, machine-set Arabic pages in different fonts and layouts, run through the same degradation and background-compositing process as the handwritten set. The result is large volumes of paired (degraded image → ground truth) samples, useful for training denoising, binarization, and recognition models that need to be robust to real scan artifacts. Ground truth is again provided at multiple granularities, matching the handwritten subset's format so both can be trained on side by side.

🔗 **[Download SDADDS-Guelma](https://zenodo.org/records/10896124)** — official dataset page (Zenodo).

<p align="center">
  <img src="SDADDS-Guelma_Printed\Degraded_IMG\Comb+Show_through\PR1Kufi_BG24-ST.jpg" alt="SDADDS-Guelma printed sample" width="420"><br>
</p>

## 4. `ahmedheakl.ipynb`

Pulls the BCE-layout split of `ahmedheakl`'s **KITAB-Bench** project straight from the Hugging Face Hub with `load_dataset("ahmedheakl/arocrbench_bcelayout")`. KITAB-Bench (ACL 2025) is a multi-domain Arabic OCR / document-understanding benchmark that repackages BCE-Arabic-v1 (alongside DocLayNet) specifically for layout-detection evaluation. The notebook loads a handful of samples and draws their ground-truth boxes over the page images — the same visual sanity-check approach used by `make_data/visual.ipynb` below, just against an external, already-published benchmark instead of our own generated data.

---

## 5. `make_data/` — our synthetic layout generator

The goal of this folder is to generate large numbers of `(image, layout-annotation)` pairs for OCR training — content that is entirely in Arabic, spread across dozens of fonts and colors and at least twenty distinct page structures (multi-column tables, merged cells, charts, mixed headings, etc.), so downstream models see genuine layout diversity rather than a handful of repeated templates.

| File | What it does |
|---|---|
| **`scrape_arabic.py`** | Crawls page by page through books on `shamela.ws`, pulling the raw Arabic text out of each page (falling back to `<p>` tags if the main content block isn't found) and appending it to one flat corpus file, `shamela_1M_words.txt`, until roughly a million words have been collected. On a failed page or empty result it just moves to the next book. This is a one-off step, re-run only to refresh or grow the corpus. |
| **`scrape_images.py`** | Downloads a thousand placeholder photographs from the Picsum random-image API into `nature_images/`, one file per index. These stand in for the photos that get dropped into any "figure" blocks the generator produces, and the folder can be swapped for any other image collection as long as the formats are Pillow-readable (png/jpg/jpeg/webp/gif). |
| **`script.py`** | The core generator. For every sample it randomly composes an A4-page grid (2–4 rows, 1–3 columns per row) and fills each cell with a heading, a justified paragraph (optionally in 2–3 newspaper-style columns), a table, or a figure, each drawn from a pool of 26 Arabic web fonts and ~28 colors. Playwright renders the resulting HTML/CSS and screenshots it, an in-browser pass auto-shrinks any text or table that overflows its cell, and finally every layout element's exact bounding box and recognized text is written out to a matching JSON file next to the PNG. |
| **`visual.ipynb`** | A quick QA notebook: given a sample name, it loads the matching PNG/JSON pair and draws every element's bounding box on top of the page in a distinct color (heading = red, paragraph = blue, figure = green, caption = amber, table = purple, table-cell = pink) with matplotlib — the fastest way to confirm the generator's boxes actually line up with the visible content before trusting a full batch. |

### Sample output

Five pages generated end-to-end by `script.py`, showing the range of headings, multi-column paragraphs, tables, and figure blocks the pipeline produces:

<table>
<tr>
<td><img src="make_data\dataset\images\sample_0000018.png" width="180"></td>
<td><img src="make_data\dataset\images\sample_0000019.png" width="180"></td>
<td><img src="make_data\dataset\images\sample_0000077.png" width="180"></td>
<td><img src="make_data\dataset\images\sample_0000023.png" width="180"></td>
<td><img src="make_data\dataset\images\sample_0000011.png" width="180"></td>
</tr>
</table>

And the same idea `visual.ipynb` is built for — one of the samples above with its ground-truth boxes drawn on top:

<p align="center">
  <img src="make_data\dataset\images\output.png" width="360">
</p>

Each generated sample is a pair of files:

```
dataset/images/sample_0000004.png        # the rendered A4 page
dataset/annotations/sample_0000004.json  # every layout-node's label, text, and bbox
```

```json
{
  "boxes": [
    {
      "label": "heading",
      "text": "تلعب التكنولوجيا الحديثة دورا ...",
      "x": 40, "y": 40, "width": 714, "height": 104.3,
      "bottom": 144.3, "right": 754
    },
    { "label": "paragraph", "text": "...", "x": 529.3, "y": 164.3, "width": 224.7, "height": 312.9 }
  ]
}
```

## Requirements

The `make_data/` scripts and notebook need the following installed via pip: `playwright`, `tqdm`, `requests`, `beautifulsoup4`, `matplotlib`, `pillow`, and `nest_asyncio`. After installing, run `playwright install chromium` once to download the actual browser binary that `script.py` uses to render and screenshot each page — pip alone doesn't include it, so generation will fail until this step is done.

```bash
pip install playwright tqdm requests beautifulsoup4 matplotlib pillow nest_asyncio
playwright install chromium
```
