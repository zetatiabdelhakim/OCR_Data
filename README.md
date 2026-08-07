# Open Arabic Document-Layout Datasets & Unified Randomized-Layout Generation

This repository brings together the Arabic document-layout resources we have assembled to train and evaluate our OCR and document-understanding models . We have combined established, third-party benchmarks with our home-grown synthetic generation pipelines—including our newly integrated unified template generator—that produce fully-Arabic, randomly-laid-out page images with pixel-accurate bounding-box ground truth .

## 📁 Repository Structure

```text
.
├── BCE-Arabic-v1/                  # Public DLA benchmark (scanned book pages)
├── SDADDS-Guelma_Handwritten/      # Synthetic degraded handwritten Arabic pages
├── SDADDS-Guelma_Printed/          # Synthetic degraded printed Arabic pages
├── ahmedheakl.ipynb                # Loads the BCE-layout split from Hugging Face
├── make_data/                      # Legacy synthetic layout generator
│   ├── dataset/                    
│   ├── nature_images/
│   ├── readme_image_ref/
│   ├── scrape_arabic.py
│   ├── scrape_images.py
│   ├── script.py                   # Original A4 grid generator
│   ├── script_charts_focus.py      # A4 charts layout
│   ├── script_equation_focus.py    # A4 equations layout
│   ├── script_image_focus.py       # A4 image gallery layout
│   ├── script_text_focus.py        # A4 dense text layout
│   ├── shamela_1M_words.txt
│   ├── visual.ipynb
│   └── template_based_ocr_dataset_gen/ # NEW: Unified Template-Based Generator
│       ├── core/                       # Shared rendering engine
│       ├── templates/                  # 13 diverse document genre definitions
│       ├── generate.py                 # Single unified launcher
│       └── README.md
```

---

## 1. `BCE-Arabic-v1/`

A published Arabic Document Layout Analysis (DLA) benchmark, originally introduced by Saad et al. (2016), built from 1,833 scanned pages drawn from 180 books to cover a wide range of real Arabic page layouts — multi-column text, tables, embedded photos, and mixed typefaces . This folder holds a working subset of roughly 1,200 sample page images used here for layout-detection experiments . It also ships a small notebook that lets you pick a target block type (heading / paragraph / table / figure) and a sample image, then renders that sample's ground-truth bounding boxes on top for a quick visual check .

<p align="center">
  <img src="BCE-Arabic v1\multi-columns\d-0.jpg" alt="BCE-Arabic-v1 sample page" width="420"><br>
</p>

## 2. `SDADDS-Guelma_Handwritten/`

The handwritten half of **SDADDS-Guelma** (Synthetic Degraded Arabic Document Data Set), created by Dr. Abderrahmane Kefali's team at the University of Guelma . Real handwritten Arabic page images are synthetically degraded and composited over a variety of paper textures and historical backgrounds (stains, folds, faded ink, uneven lighting) to mimic real archival wear . Each generated image ships with ground truth at the text-line, word, and connected-component level . 

🔗 **[Download SDADDS-Guelma](https://zenodo.org/records/10896124)** — official dataset page (Zenodo) .

<p align="center">
  <img src="SDADDS-Guelma_Handwritten\HW1Fix_BG15-CU.jpg" alt="SDADDS-Guelma handwritten sample" width="420"><br>
</p>

## 3. `SDADDS-Guelma_Printed/`

The printed-text counterpart of the same SDADDS-Guelma pipeline: clean, machine-set Arabic pages in different fonts and layouts, run through the same degradation and background-compositing process as the handwritten set . The result is large volumes of paired (degraded image → ground truth) samples, useful for training denoising, binarization, and recognition models that need to be robust to real scan artifacts . 

🔗 **[Download SDADDS-Guelma](https://zenodo.org/records/10896124)** — official dataset page (Zenodo) .

<p align="center">
  <img src="SDADDS-Guelma_Printed\PR1Kufi_BG14-ST.jpg" alt="SDADDS-Guelma printed sample" width="420"><br>
</p>

## 4. `ahmedheakl.ipynb`

Pulls the BCE-layout split of `ahmedheakl`'s **KITAB-Bench** project straight from the Hugging Face Hub with `load_dataset("ahmedheakl/arocrbench_bcelayout")` . KITAB-Bench (ACL 2025) is a multi-domain Arabic OCR / document-understanding benchmark that repackages BCE-Arabic-v1 (alongside DocLayNet) specifically for layout-detection evaluation . The notebook loads a handful of samples and draws their ground-truth boxes over the page images .

---

## 5. `make_data/` — Legacy Layout Generator

*(Note: The older scripts listed below remain fully functional for generating specific,  A4 layouts  .)*

The goal of this folder is to generate large numbers of `(image, layout-annotation)` pairs for OCR training — content that is entirely in Arabic, spread across dozens of fonts and colors . We initially split this across five targeted scripts before moving to the new unified pipeline  .

| File | What it does |
|---|---|
| **`scrape_arabic.py`** | Crawls page by page through books on `shamela.ws`, pulling raw Arabic text into `shamela_1M_words.txt` . |
| **`scrape_images.py`** | Downloads a thousand placeholder photographs from the Picsum random-image API into `nature_images/` . |
| **`script.py`** | The core legacy generator. It randomly composes an A4-page grid (2–4 rows, 1–3 columns per row) and fills each cell with headings, paragraphs, tables, or figures . |
| **`script_charts_focus.py`** | A specialized script  to produce A4 layouts heavily focused on statistical charts  . |
| **`script_equation_focus.py`** | A specialized script  to produce A4 layouts heavily focused on mathematical equations  . |
| **`script_image_focus.py`** | A specialized script  to produce A4 layouts heavily focused on image galleries and figures  . |
| **`script_text_focus.py`** | A specialized script  to produce A4 layouts focusing on dense, multi-column Arabic text blocks  . |
| **`visual.ipynb`** | A quick QA notebook that draws every element's bounding box on top of the page in a distinct color to visually confirm alignment . |

### Sample output (Legacy Pipeline)

Five pages generated end-to-end by `script.py`:

<table>
<tr>
<td><img src="make_data\readme_image_ref\1.png" width="180"></td>
<td><img src="make_data\readme_image_ref\2.png" width="180"></td>
<td><img src="make_data\readme_image_ref\3.png" width="180"></td>
<td><img src="make_data\readme_image_ref\4.png" width="180"></td>
<td><img src="make_data\readme_image_ref\5.png" width="180"></td>
</tr>
</table>

And the matching `visual.ipynb` ground-truth output:

<p align="center">
  <img src="make_data\readme_image_ref\visual_ref.png" width="360">
</p>

---

## 6. `template_based_ocr_dataset_gen/` — New Unified Generator

To dramatically scale our capabilities, we have introduced a new, unified rendering engine  . The previous setup required maintaining the 5 separate scripts described above, each  to one specific A4 style  . We have entirely replaced this approach with a single shared rendering engine (`core/`) and a unified launcher  .

This new methodology leverages `generate.py` to produce the exact same PNG and JSON annotation formats our downstream OCR pipeline already expects, but with vastly improved data diversity and architectural stability  .

### 🌟 Unmatched Document Diversity
*   **13 Distinct Document Genres:** We now generate far more than just A4 grids  . The templates support A4 reports, business cards, book covers, receipts, letters, minimalist posters, invoices, ID cards, and dense math-proof pages  .
*   **Dynamic, Real-World Sizing:** Each template declares its own real-world canvas size  . We apply an independent +/- 12% jitter to the width and height of every single generated canvas, ensuring authentic size variety even within the same genre  .
*   **Hybrid Snippet Injection:** Approximately 28% of all samples receive a random "foreign" snippet (such as a chart, an equation, a quote, or a theorem box) dropped directly into the selected template—for example, a chart inside a receipt or an equation on a book cover  .
*   **Uniform Randomization:** The launcher picks a template uniformly at random for every sample to ensure the final dataset mix feels highly organic rather than synthetically bucketed  .

### ⚙️ Setup & Team Execution Flow
Because our pipeline is collaborative and will be utilized by multiple team members, please follow this flow to ensure it runs properly on your local environment.

**Step 1: Install Dependencies**
We use Playwright to handle the complex headless HTML/CSS rendering  .
```bash
pip install playwright tqdm nest_asyncio
playwright install chromium --with-deps
```

**Step 2: Asset Prerequisites**
Ensure you have our shared assets in place at the root level before running:
*   `../shamela_1M_words.txt`: Our scraped Arabic text corpus  .
*   `../nature_images/`: Our downloaded photos for book covers and figures  .

**Step 3: Run the Generator**
Simply execute the unified launcher. The system will automatically handle the asynchronous generation, uniform template selection, and JSON annotation extraction  .
```bash
cd template_based_ocr_dataset_gen
python generate.py
```

Output files will automatically route to `../dataset/images/sample_XXXXXXX.png` and `../dataset/annotations/sample_XXXXXXX.json` (maintaining the identical convention as our earlier scripts so all downstream code remains fully compatible)  .

*(Note: Ensure you have an active internet connection during execution. The rendering engine fetches Google Fonts, KaTeX, and Chart.js from their public CDNs  . If you are in a locked-down sandbox or CI environment, math and charts will gracefully render empty rather than crashing the generation run, and everything else will render correctly  .)*