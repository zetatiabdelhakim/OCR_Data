# Getting the demo font files

This folder needs 6 small `.ttf` files to match `demo_fonts_manifest.csv`. I couldn't
download them directly into this project (no internet access in the environment that
built this folder), but they're all free, open-licensed (SIL Open Font License) fonts
from Google Fonts, safe to redistribute in a public repo.

Download each one from Google Fonts and place the `.ttf` file directly in this
`fonts/demo/` folder, matching these exact filenames:

| File to save as | Google Fonts page |
|---|---|
| `Amiri-Regular.ttf` | https://fonts.google.com/specimen/Amiri |
| `AmiriQuran-Regular.ttf` | https://fonts.google.com/specimen/Amiri+Quran |
| `ReemKufi-Regular.ttf` | https://fonts.google.com/specimen/Reem+Kufi |
| `Lateef-Regular.ttf` | https://fonts.google.com/specimen/Lateef |
| `ArefRuqaa-Regular.ttf` | https://fonts.google.com/specimen/Aref+Ruqaa |
| `Jomhuria-Regular.ttf` | https://fonts.google.com/specimen/Jomhuria |

On each page: click **Download family**, unzip, find the `Regular` `.ttf` inside, and
rename/move it here.

Once all 6 are in place, `generation_config.demo.json` will work immediately, and
`generate_readme_assets.py` will be able to render the example images for the README.

You can delete this file once the fonts are in place.
