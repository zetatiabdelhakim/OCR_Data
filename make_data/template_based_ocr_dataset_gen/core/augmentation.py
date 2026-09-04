"""
core/augmentation.py
====================
Data augmentation pipeline for the OCR dataset generator.
Applies one of 10 predefined augmentations to each generated image,
updating the JSON annotation when the augmentation changes dimensions.

JSON schema for the ``augmentation`` field:
  Original image  → "augmentation": null
  Augmented image → "augmentation": {"name": "<name>", "params": { ... }}

All parameters applied are fully recorded in the params dict so the
dataset consumer can reproduce or filter by exact augmentation settings.

Design principles:
  - All parameters are conservative so text remains human-readable
  - Only Rotation changes image dimensions (and thus annotation coords)
  - Each augmentation is applied individually (not via Augraphy pipeline)
  - Failures are handled gracefully — a failed augmentation returns False
"""

import os
import json
import copy
import random

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

from augraphy import (
    BadPhotoCopy,
    BleedThrough,
    ColorShift,
    Letterpress,
    ReflectedLight,
    ShadowCast,
)

# -----------------------------------------------------------------------
# Config — output format for augmented images only. Originals (written by
# the render engine) are always lossless PNG and are never touched here.
# -----------------------------------------------------------------------
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _config = yaml.safe_load(_f)

AUGMENTATION_OUTPUT_FORMAT = str(_config.get("augmentation_output_format", "png")).lower()
AUGMENTATION_JPEG_QUALITY = int(_config.get("augmentation_jpeg_quality", 92))

# -----------------------------------------------------------------------
# Registry of all 10 augmentation names & sampling weights
# -----------------------------------------------------------------------
AUGMENTATION_NAMES = [
    "gaussian_blur",
    "bad_photocopy",
    "bleed_through",
    "color_shift",
    "letterpress",
    "rotation",
    "reflected_light",
    "shadow_cast",
    "watermark",
    "gaussian_noise",
]

# Weights configure relative selection probability:
# watermark has weight 1.0 (relative probability 1/40 = 2.5%),
# other 9 augmentations share the remaining 39.0 weight equally (4.333 each).
AUGMENTATION_WEIGHTS = {
    name: 39.0 / 9.0 for name in AUGMENTATION_NAMES
}
AUGMENTATION_WEIGHTS["watermark"] = 1.0

# Curated Arabic watermark words — pre-selected so the word is known at annotation time
_WATERMARK_WORDS = [
    "سري", "نسخة", "مسودة", "للمراجعة", "نموذج", "أصلي", "خاص",
    "محدود التداول", "سري للغاية", "مؤقت", "معتمد", "نسخة مطابقة للأصل",
]

_WATERMARK_FONTS_CACHE = []


def pick_n_distinct(n=3, weights=None):
    """Pick n different augmentation names via weighted sampling without replacement."""
    w_map = weights or AUGMENTATION_WEIGHTS
    pool = list(AUGMENTATION_NAMES)
    w_pool = [w_map.get(name, 1.0) for name in pool]
    chosen = []

    for _ in range(min(n, len(pool))):
        total_w = sum(w_pool)
        if total_w <= 0:
            break
        r = random.uniform(0, total_w)
        upto = 0.0
        for i, w in enumerate(w_pool):
            upto += w
            if upto >= r:
                chosen.append(pool.pop(i))
                w_pool.pop(i)
                break

    return chosen


# -----------------------------------------------------------------------
# Safe Augraphy wrapper
# -----------------------------------------------------------------------

def _safe_augraphy(aug_class, img, **kwargs):
    """Create and apply an Augraphy augmentation with defensive fallbacks."""
    for attempt_kwargs in [dict(**kwargs, p=1.0), dict(p=1.0)]:
        try:
            aug = aug_class(**attempt_kwargs)
            result = aug(img)
            if isinstance(result, tuple):
                result = result[0]
            if isinstance(result, np.ndarray) and result.size > 0:
                return result
        except TypeError:
            continue
        except Exception:
            continue
    return img


# -----------------------------------------------------------------------
# Individual augmentation functions
# Each returns (augmented_image, params_dict)
# -----------------------------------------------------------------------

def _apply_gaussian_blur(img):
    """Mild Gaussian blur — text stays sharp enough to read."""
    k = random.choice([3, 5])
    kernel_size = (k, k)
    result = cv2.GaussianBlur(img, kernel_size, sigmaX=0)
    return result, {"kernel_size": [k, k]}


def _apply_bad_photocopy(img):
    """Light photocopy artifacts — text remains clear."""
    noise_type = -1
    noise_iteration = (1, 2)
    noise_size = (1, 2)
    noise_value = (0, 30)
    noise_sparsity = (0.3, 0.5)
    noise_concentration = (0.1, 0.3)
    result = _safe_augraphy(
        BadPhotoCopy, img,
        noise_type=noise_type,
        noise_iteration=noise_iteration,
        noise_size=noise_size,
        noise_value=noise_value,
        noise_sparsity=noise_sparsity,
        noise_concentration=noise_concentration,
    )
    return result, {
        "noise_type": noise_type,
        "noise_iteration": list(noise_iteration),
        "noise_size": list(noise_size),
        "noise_value": list(noise_value),
        "noise_sparsity": list(noise_sparsity),
        "noise_concentration": list(noise_concentration),
    }


def _apply_bleed_through(img):
    """Gentle ink bleed-through from back side of paper."""
    alpha = round(random.uniform(0.1, 0.2), 2)
    intensity_range = (0.05, 0.15)
    ksize = (17, 17)
    offsets = (10, 20)
    result = _safe_augraphy(
        BleedThrough, img,
        intensity_range=intensity_range,
        ksize=ksize,
        sigmaX=0,
        alpha=alpha,
        offsets=offsets,
    )
    return result, {
        "alpha": alpha,
        "intensity_range": list(intensity_range),
        "ksize": list(ksize),
        "offsets": list(offsets),
    }


def _apply_color_shift(img):
    """Tiny channel misalignment — barely noticeable printing defect."""
    offset_x_range = (1, 3)
    offset_y_range = (1, 3)
    result = _safe_augraphy(
        ColorShift, img,
        color_shift_offset_x_range=offset_x_range,
        color_shift_offset_y_range=offset_y_range,
    )
    return result, {
        "offset_x_range": list(offset_x_range),
        "offset_y_range": list(offset_y_range),
    }


def _apply_letterpress(img):
    """Light debossed/pressed text texture."""
    n_samples = (100, 300)
    n_clusters = (200, 500)
    std_range = (500, 3000)
    value_range = (150, 224)
    value_threshold_range = (96, 128)
    result = _safe_augraphy(
        Letterpress, img,
        n_samples=n_samples,
        n_clusters=n_clusters,
        std_range=std_range,
        value_range=value_range,
        value_threshold_range=value_threshold_range,
    )
    return result, {
        "n_samples": list(n_samples),
        "n_clusters": list(n_clusters),
        "std_range": list(std_range),
        "value_range": list(value_range),
        "value_threshold_range": list(value_threshold_range),
    }


def _apply_rotation(img):
    """Slight tilt like a skewed scan (±5 degrees max).
    This is the ONLY augmentation that changes image dimensions."""
    angle = round(random.uniform(-5, 5), 1)
    if abs(angle) < 0.5:
        angle = random.choice([-2.0, 2.0])

    h, w = img.shape[:2]
    cx, cy = w / 2.0, h / 2.0

    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)

    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)

    M[0, 2] += (new_w - w) / 2.0
    M[1, 2] += (new_h - h) / 2.0

    result = cv2.warpAffine(
        img, M, (new_w, new_h),
        borderValue=(255, 255, 255),
    )
    return result, {
        "angle": angle,
        "fill_color": [255, 255, 255],
        "_matrix": M,              # internal: used by transform_annotation
        "_new_size": (new_w, new_h),
    }


def _apply_reflected_light(img):
    """Soft glare / shiny spot on paper surface."""
    smoothness = 2.5
    internal_radius_range = (0.05, 0.1)
    external_radius_range = (0.20, 0.40)
    result = _safe_augraphy(
        ReflectedLight, img,
        reflected_light_smoothness=smoothness,
        reflected_light_internal_radius_range=internal_radius_range,
        reflected_light_external_radius_range=external_radius_range,
    )
    return result, {
        "smoothness": smoothness,
        "internal_radius_range": list(internal_radius_range),
        "external_radius_range": list(external_radius_range),
    }


def _apply_shadow_cast(img):
    """Gentle, realistic shadow falling across the document."""
    opacity = round(random.uniform(0.2, 0.4), 2)
    width_range = (0.3, 0.5)
    height_range = (0.3, 0.5)
    shadow_side = "random"
    result = _safe_augraphy(
        ShadowCast, img,
        shadow_side=shadow_side,
        shadow_vertices_range=(2, 4),
        shadow_width_range=width_range,
        shadow_height_range=height_range,
        shadow_color=(0, 0, 0),
        shadow_opacity_range=(opacity, min(opacity + 0.05, 0.5)),
    )
    return result, {
        "shadow_side": shadow_side,
        "opacity": opacity,
        "width_range": list(width_range),
        "height_range": list(height_range),
    }


def _get_watermark_font(size):
    """Retrieve an authentic Arabic font from assets or fallback system fonts."""
    global _WATERMARK_FONTS_CACHE
    try:
        from core import assets
        if not _WATERMARK_FONTS_CACHE and hasattr(assets, "FONTS_FOLDER_PATH"):
            fdir = assets.FONTS_FOLDER_PATH
            if os.path.exists(fdir):
                for root, _, files in os.walk(fdir):
                    for f in files:
                        if f.lower().endswith(('.ttf', '.otf')) and not f.startswith('.'):
                            _WATERMARK_FONTS_CACHE.append(os.path.join(root, f))
    except Exception:
        pass

    # 1. Try fonts loaded from the fonts directory
    if _WATERMARK_FONTS_CACHE:
        for _ in range(5):
            font_path = random.choice(_WATERMARK_FONTS_CACHE)
            try:
                return ImageFont.truetype(font_path, size), os.path.basename(font_path)
            except Exception:
                continue

    # 2. Try common system TrueType fonts supporting Arabic
    sys_fonts = [
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for sf in sys_fonts:
        if os.path.exists(sf):
            try:
                return ImageFont.truetype(sf, size), os.path.basename(sf)
            except Exception:
                continue

    return ImageFont.load_default(), "default"


def _apply_watermark(img):
    """Faded, low-contrast Arabic watermark text overlay.
    Properly shaped and bi-directionally rendered via PIL + arabic_reshaper + python-bidi.
    The parameters are fully recorded in the JSON annotation params."""
    h, w = img.shape[:2]

    word = random.choice(_WATERMARK_WORDS)
    try:
        reshaped_text = arabic_reshaper.reshape(word)
        bidi_text = get_display(reshaped_text)
    except Exception:
        bidi_text = word

    # Dynamic font size proportional to document dimensions
    min_dim = min(h, w)
    font_size = random.randint(max(24, int(min_dim * 0.07)), max(36, int(min_dim * 0.14)))
    font_size = max(20, min(font_size, 160))

    font, font_name = _get_watermark_font(font_size)

    # Measure text dimensions
    try:
        bbox = font.getbbox(bidi_text)
        tw = max(10, bbox[2] - bbox[0])
        th = max(10, bbox[3] - bbox[1])
        offset_x = bbox[0]
        offset_y = bbox[1]
    except Exception:
        tw, th = len(word) * (font_size // 2), font_size
        offset_x, offset_y = 0, 0

    # Curated authentic watermark color schemes
    color_schemes = [
        ("gray", (100, 100, 100)),
        ("charcoal", (60, 60, 60)),
        ("red_stamp", (180, 40, 40)),
        ("blue_stamp", (30, 80, 160)),
        ("amber_stamp", (160, 110, 20)),
    ]
    color_name, rgb = random.choice(color_schemes)

    # Transparency / alpha: 30 to 75 (out of 255) -> realistic 12% - 29% opacity
    alpha = random.randint(30, 75)
    rgba_color = (rgb[0], rgb[1], rgb[2], alpha)

    # Create transparent text tile
    pad = 24
    tile_w = tw + pad * 2
    tile_h = th + pad * 2
    tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)

    # Draw text centered in the tile
    draw.text((pad - offset_x, pad - offset_y), bidi_text, font=font, fill=rgba_color)

    # 35% chance to add a subtle stamp border box
    has_border = random.random() < 0.35
    if has_border:
        draw.rectangle([4, 4, tile_w - 5, tile_h - 5], outline=rgba_color, width=max(2, font_size // 22))

    # Rotation
    angle = random.choice([-45, -35, -30, -20, -15, 0, 15, 20, 30, 35, 45])
    rotated_tile = tile.rotate(angle, expand=True, resample=Image.Resampling.BILINEAR)
    rw, rh = rotated_tile.size

    # Location placement
    location_choices = ["center", "top_right", "bottom_left", "diagonal"]
    loc = random.choice(location_choices)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if loc in ("center", "diagonal"):
        pos_x = (w - rw) // 2
        pos_y = (h - rh) // 2
    elif loc == "top_right":
        pos_x = max(0, w - rw - random.randint(20, max(21, w // 8)))
        pos_y = random.randint(20, max(21, h // 8))
    else:  # bottom_left
        pos_x = random.randint(20, max(21, w // 8))
        pos_y = max(0, h - rh - random.randint(20, max(21, h // 8)))

    overlay.paste(rotated_tile, (pos_x, pos_y), rotated_tile)

    # Alpha blend onto original image
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_base = Image.fromarray(img_rgb).convert("RGBA")
    composite = Image.alpha_composite(pil_base, overlay).convert("RGB")
    result_bgr = cv2.cvtColor(np.array(composite), cv2.COLOR_RGB2BGR)

    return result_bgr, {
        "word": word,
        "font": font_name,
        "font_size": font_size,
        "angle": angle,
        "opacity": round(alpha / 255.0, 3),
        "color": color_name,
        "location": loc,
        "has_stamp_border": has_border,
    }


def _apply_gaussian_noise(img):
    """Light sensor noise from camera/scanner."""
    sigma = random.randint(5, 15)
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    noisy = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return noisy, {"sigma": sigma}


# -----------------------------------------------------------------------
# Dispatch table
# -----------------------------------------------------------------------
_AUGMENTATION_FN = {
    "gaussian_blur":    _apply_gaussian_blur,
    "bad_photocopy":    _apply_bad_photocopy,
    "bleed_through":    _apply_bleed_through,
    "color_shift":      _apply_color_shift,
    "letterpress":      _apply_letterpress,
    "rotation":         _apply_rotation,
    "reflected_light":  _apply_reflected_light,
    "shadow_cast":      _apply_shadow_cast,
    "watermark":        _apply_watermark,
    "gaussian_noise":   _apply_gaussian_noise,
}


def apply_augmentation(name, img):
    """Apply one named augmentation. Returns (augmented_image, params_dict)."""
    return _AUGMENTATION_FN[name](img)


# -----------------------------------------------------------------------
# Annotation coordinate transformation
# -----------------------------------------------------------------------

def _rotate_bbox(block, M, new_w, new_h, coord_keys):
    """Rotate a bounding box through affine matrix M, return axis-aligned result."""
    x1 = block[coord_keys[0]]
    y1 = block[coord_keys[1]]
    x2 = block[coord_keys[2]]
    y2 = block[coord_keys[3]]

    corners = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float64)
    ones = np.ones((4, 1), dtype=np.float64)
    corners_h = np.hstack([corners, ones])
    transformed = (M @ corners_h.T).T

    rx1 = max(0, int(round(transformed[:, 0].min())))
    ry1 = max(0, int(round(transformed[:, 1].min())))
    rx2 = min(new_w, int(round(transformed[:, 0].max())))
    ry2 = min(new_h, int(round(transformed[:, 1].max())))

    if rx2 <= rx1 + 5 or ry2 <= ry1 + 5:
        return None

    block[coord_keys[0]] = rx1
    block[coord_keys[1]] = ry1
    block[coord_keys[2]] = rx2
    block[coord_keys[3]] = ry2
    return block


def transform_annotation(name, annotation, params, old_shape, new_shape):
    """Return an updated copy of the annotation dict.

    Updates the ``meta.augmentation`` field with the full params dict
    using the schema: {"name": "<name>", "params": { ... }}.

    For rotation (the only dimension-changing augmentation), also rotates
    every block and image bounding box.
    """
    ann = copy.deepcopy(annotation)

    if "meta" not in ann:
        ann["meta"] = {}

    # Strip internal params (prefixed with _) from the public record
    public_params = {k: v for k, v in params.items() if not k.startswith("_")}

    # New schema: {"name": ..., "params": {...}}
    ann["meta"]["augmentation"] = {
        "name": name,
        "params": public_params,
    }

    if name != "rotation":
        return ann

    # ---- Rotation-specific coordinate updates ----
    M = params["_matrix"]
    new_w, new_h = params["_new_size"]

    ann["dimensions"]["width"] = new_w
    ann["dimensions"]["height"] = new_h

    coord_keys = ("top_left_x", "top_left_y", "bottom_right_x", "bottom_right_y")

    updated_blocks = []
    for block in ann.get("blocks", []):
        result = _rotate_bbox(block, M, new_w, new_h, coord_keys)
        if result is not None:
            updated_blocks.append(result)
    ann["blocks"] = updated_blocks

    updated_images = []
    for img_entry in ann.get("images", []):
        result = _rotate_bbox(img_entry, M, new_w, new_h, coord_keys)
        if result is not None:
            updated_images.append(result)
    ann["images"] = updated_images

    return ann


# -----------------------------------------------------------------------
# Main entry point — used by generate.py worker processes
# -----------------------------------------------------------------------

def augment_sample(img_path, json_path, out_img_path, out_json_path, aug_name):
    """Load original image + JSON → apply one augmentation → save the pair.

    Returns (success: bool, error_message: str | None). Runs inside a worker
    subprocess (via the multiprocessing pool) — it must never print directly,
    since that can corrupt the main process's live progress bars; any error
    detail is returned instead, for the main process to log.
    """
    img = cv2.imread(img_path)
    if img is None:
        return False, f"could not read image: {img_path}"

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            annotation = json.load(f)
    except Exception as e:
        return False, f"could not read annotation {json_path}: {e}"

    try:
        augmented_img, params = apply_augmentation(aug_name, img)
    except Exception as e:
        return False, f"'{aug_name}' failed on {img_path}: {e}"

    if augmented_img is None or augmented_img.size == 0:
        return False, f"'{aug_name}' produced an empty image for {img_path}"

    new_annotation = transform_annotation(
        aug_name, annotation, params, img.shape, augmented_img.shape
    )

    try:
        # cv2.imwrite reports failure by RETURNING False — it does not raise.
        # Ignoring that return is how the published dataset ended up with
        # thousands of annotations whose image was never written: the JSON
        # below still got created and the caller was told the pair succeeded.
        # The image must exist and be non-empty before the annotation is
        # written, so a half-written pair can never reach a shard.
        if AUGMENTATION_OUTPUT_FORMAT == "jpeg":
            out_img_path = os.path.splitext(out_img_path)[0] + ".jpg"
            wrote = cv2.imwrite(out_img_path, augmented_img,
                                [cv2.IMWRITE_JPEG_QUALITY, AUGMENTATION_JPEG_QUALITY])
        else:
            wrote = cv2.imwrite(out_img_path, augmented_img)

        if not wrote:
            return False, f"cv2.imwrite returned False for {out_img_path}"
        if not os.path.exists(out_img_path) or os.path.getsize(out_img_path) == 0:
            try:
                os.remove(out_img_path)
            except OSError:
                pass
            return False, f"'{aug_name}' wrote an empty image at {out_img_path}"

        # Compact separators, no indent: annotations are ~20% of the dataset's
        # bytes and indent=4 inflates them by roughly a third for no gain.
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(new_annotation, f, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        return False, f"failed writing output for {out_img_path}: {e}"

    return True, None
