"""
core/assets.py
================
Shared assets, corpus access and sizing helpers used by every template.
Nothing in here renders HTML - it only provides raw materials.
"""

import os
import random
import base64
import mimetypes
import pandas as pd

import yaml

# ------------------------------------------------------------------
# Paths (edit these to match your local setup)
# ------------------------------------------------------------------

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

IMAGE_FOLDER_PATH = config.get("nature_images_dir", "../nature_images")

# These will be updated dynamically by generate.py for each chunk
DATASET_IMAGES_PATH = "../dataset/images"
DATASET_ANNOTATIONS_PATH = "../dataset/annotations"

FONTS_FOLDER_PATH = config.get("fonts_dir", "./../fonts")

IMAGE_PATHS = []
FONTS = []
DISPLAY_FONTS = []
FONT_FACE_DICT = {}

COLORS = [
    "#000000", "#111111", "#1f1f1f", "#2d2d2d", "#404040", "#555555", "#666666",
    "#1e3a8a", "#1d4ed8", "#2563eb", "#1e40af", "#0f172a", "#14532d", "#166534",
    "#15803d", "#0f766e", "#7f1d1d", "#991b1b", "#b91c1c", "#dc2626", "#4c1d95",
    "#6d28d9", "#78350f", "#92400e", "#854d0e", "#334155", "#475569",
]

# A handful of small, fixed boilerplate pools. These are structural
# phrases (salutations, closings...) rather than a full lexicon - kept
# deliberately tiny since content realism is not the point, layout is.

LETTER_OPENERS = ["السيد المحترم،", "السيدة المحترمة،", "إلى من يهمه الأمر،", "حضرة السيد المدير المحترم،"]
LETTER_INTROS = ["تحية طيبة وبعد،", "يشرفني أن أتوجه إليكم بخصوص", "أتقدم إليكم بهذه الرسالة من أجل"]
LETTER_CLOSINGS = ["وتفضلوا بقبول فائق الاحترام والتقدير.", "وفي انتظار ردكم، تقبلوا أسمى عبارات التقدير.",
                    "شاكرين لكم حسن تعاونكم."]

RECEIPT_HEADER_WORDS_MIN, RECEIPT_HEADER_WORDS_MAX = 2, 4


# ------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------

def load_assets():
    global CORPUS_WORDS, IMAGE_PATHS, FONTS, DISPLAY_FONTS, FONT_FACE_DICT


    if os.path.exists(IMAGE_FOLDER_PATH):
        print(f"Scanning images in {IMAGE_FOLDER_PATH}...")
        valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        IMAGE_PATHS = [
            os.path.join(IMAGE_FOLDER_PATH, f) for f in os.listdir(IMAGE_FOLDER_PATH)
            if f.lower().endswith(valid_extensions)
        ]
    else:
        raise FileNotFoundError(f"{IMAGE_FOLDER_PATH} not found.")

    if os.path.exists(FONTS_FOLDER_PATH):
        print(f'Loading fonts from {FONTS_FOLDER_PATH}...')
        file_path = f"{FONTS_FOLDER_PATH}/fonts_manifest_all_with_images.xlsx"
        df = pd.read_excel(file_path)
        valid_fonts = df[df["blacklisted"] == False]
        if valid_fonts.empty:
            raise ValueError("Aucune police valide trouvée.")

        for i, valid_font in enumerate(valid_fonts['file_path'].tolist()):
            font_path = valid_font.replace("./fonts", FONTS_FOLDER_PATH, 1)
            if not os.path.exists(font_path):
                continue
                
            font_name = f"CustomFont_{i}"
            FONTS.append(font_name)
            
            mime_type, _ = mimetypes.guess_type(font_path)
            if not mime_type:
                mime_type = "font/ttf"
                
            with open(font_path, "rb") as font_file:
                encoded_font = base64.b64encode(font_file.read()).decode('utf-8')
                
            FONT_FACE_DICT[font_name] = f"@font-face {{ font-family: '{font_name}'; src: url('data:{mime_type};base64,{encoded_font}'); }}\n"

        DISPLAY_FONTS = FONTS
    else:
        raise FileNotFoundError(f"{FONTS_FOLDER_PATH} not found.")




from .text_provider import current_document

def get_real_arabic_text(min_words=30, max_words=300):
    doc = current_document.get()
    if doc:
        return doc.get_words(min_words, max_words)
    return "نص تجريبي غير متصل"

def get_real_arabic_title():
    doc = current_document.get()
    if doc:
        return doc.get_title()
    return "عنوان تجريبي"
    
def get_real_arabic_name():
    doc = current_document.get()
    if doc:
        return doc.get_author()
    return "اسم تجريبي"


def get_image_base64(img_path):
    mime_type, _ = mimetypes.guess_type(img_path)
    if not mime_type:
        mime_type = "image/jpeg"
    with open(img_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:{mime_type};base64,{encoded_string}"


def random_image_b64():
    """Returns a base64 data URI for a random asset image, or None if no images loaded."""
    if not IMAGE_PATHS:
        return None
    return get_image_base64(random.choice(IMAGE_PATHS))


# ------------------------------------------------------------------
# Sizing helpers - real-world sizes converted to CSS px, with jitter
# ------------------------------------------------------------------

DEFAULT_DPI = config.get("default_dpi", 96)
DEFAULT_JITTER_PCT = config.get("default_jitter_pct", 0.12)


def mm_to_px(mm, dpi=DEFAULT_DPI):
    return round(mm / 25.4 * dpi)


def jitter(value, pct=DEFAULT_JITTER_PCT, min_value=40):
    factor = 1 + random.uniform(-pct, pct)
    return max(min_value, round(value * factor))


def jittered_size(width_mm, height_mm, dpi=DEFAULT_DPI, pct=DEFAULT_JITTER_PCT):
    """mm -> px, then apply independent jitter to width and height."""
    w = mm_to_px(width_mm, dpi)
    h = mm_to_px(height_mm, dpi)
    return jitter(w, pct), jitter(h, pct)


def jittered_px(width_px, height_px, pct=DEFAULT_JITTER_PCT):
    """For formats with no natural mm size (posters, social banners...):
    jitter a pair of already-in-px base dimensions directly."""
    return jitter(width_px, pct), jitter(height_px, pct)


def random_fake_phone():
    return f"0{random.choice([6, 7])}{random.randint(10000000, 99999999)}"


def random_fake_price(min_v=5, max_v=950):
    val = random.choice([random.randint(min_v, max_v), round(random.uniform(min_v, max_v), 2)])
    return f"{val:,.2f}" if isinstance(val, float) else f"{val}.00"


def random_isbn():
    return "978-" + "-".join(str(random.randint(0, 9999)) for _ in range(3)) + f"-{random.randint(0, 9)}"
