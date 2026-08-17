"""
core/augmentation.py
====================
Data augmentation pipeline for the OCR dataset generator.
Applies one of 10 predefined augmentations to each generated image,
updating the JSON annotation when the augmentation changes dimensions.

Uses Augraphy for document-specific augmentations and OpenCV/NumPy
for basic image processing augmentations (Gaussian blur, Gaussian noise).

Design principles:
  - All parameters are conservative so text remains human-readable
  - Only Rotation changes image dimensions (and thus annotation coords)
  - Each augmentation is applied individually (not via Augraphy pipeline)
  - Failures are handled gracefully — a failed augmentation returns False
    but never crashes the generation run
"""

import json
import copy
import random

import cv2
import numpy as np

# Augraphy augmentations (imported individually)
from augraphy import (
    BadPhotoCopy,
    BleedThrough,
    ColorShift,
    Letterpress,
    ReflectedLight,
    ShadowCast,
    WaterMark,
)

# -----------------------------------------------------------------------
# Registry of all 10 augmentation names
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


def pick_n_distinct(n=3):
    """Pick n different augmentation names (no repeats within the same set)."""
    return random.sample(AUGMENTATION_NAMES, min(n, len(AUGMENTATION_NAMES)))


# -----------------------------------------------------------------------
# Safe Augraphy wrapper
# -----------------------------------------------------------------------

def _safe_augraphy(aug_class, img, **kwargs):
    """Create and apply an Augraphy augmentation with defensive fallbacks.

    1. Try with the provided kwargs + p=1.0
    2. If that fails (bad param names in this Augraphy version), retry with
       only p=1.0 (all defaults)
    3. If that also fails, return the original image unchanged.
    """
    for attempt_kwargs in [dict(**kwargs, p=1.0), dict(p=1.0)]:
        try:
            aug = aug_class(**attempt_kwargs)
            result = aug(img)
            # Some Augraphy versions return (image, mask) tuples
            if isinstance(result, tuple):
                result = result[0]
            if isinstance(result, np.ndarray) and result.size > 0:
                return result
        except TypeError:
            continue  # wrong param names for this version, try defaults
        except Exception:
            continue
    return img  # all attempts failed, return original


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
    result = _safe_augraphy(
        BadPhotoCopy, img,
        noise_type=-1,
        noise_iteration=(1, 2),
        noise_size=(1, 2),
        noise_value=(0, 30),
        noise_sparsity=(0.3, 0.5),
        noise_concentration=(0.1, 0.3),
    )
    return result, {}


def _apply_bleed_through(img):
    """Gentle ink bleed-through from back side of paper."""
    alpha = round(random.uniform(0.1, 0.2), 2)
    result = _safe_augraphy(
        BleedThrough, img,
        intensity_range=(0.05, 0.15),
        ksize=(17, 17),
        sigmaX=0,
        alpha=alpha,
        offsets=(10, 20),
    )
    return result, {"alpha": alpha}


def _apply_color_shift(img):
    """Tiny channel misalignment — barely noticeable printing defect."""
    result = _safe_augraphy(
        ColorShift, img,
        color_shift_offset_x_range=(1, 3),
        color_shift_offset_y_range=(1, 3),
    )
    return result, {}


def _apply_letterpress(img):
    """Light debossed/pressed text texture."""
    result = _safe_augraphy(
        Letterpress, img,
        n_samples=(100, 300),
        n_clusters=(200, 500),
        std_range=(500, 3000),
        value_range=(150, 224),
        value_threshold_range=(96, 128),
    )
    return result, {}


def _apply_rotation(img):
    """Slight tilt like a skewed scan (±5 degrees max).

    This is the ONLY augmentation that changes image dimensions.
    Uses OpenCV directly (not Augraphy) for precise control over the
    rotation matrix — needed to accurately transform annotation coords.
    """
    angle = round(random.uniform(-5, 5), 1)
    # Avoid near-zero rotations that produce no visible effect
    if abs(angle) < 0.5:
        angle = random.choice([-2.0, 2.0])

    h, w = img.shape[:2]
    cx, cy = w / 2.0, h / 2.0

    # Build the 2×3 affine rotation matrix
    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)

    # Compute expanded canvas dimensions so nothing is cropped
    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)

    # Shift the rotation centre to the new canvas centre
    M[0, 2] += (new_w - w) / 2.0
    M[1, 2] += (new_h - h) / 2.0

    result = cv2.warpAffine(
        img, M, (new_w, new_h),
        borderValue=(255, 255, 255),  # white fill for expanded edges
    )
    return result, {
        "angle": angle,
        "_matrix": M,             # internal: used by transform_annotation
        "_new_size": (new_w, new_h),
    }


def _apply_reflected_light(img):
    """Soft glare / shiny spot on paper surface."""
    result = _safe_augraphy(
        ReflectedLight, img,
        reflected_light_smoothness=2.5,
        reflected_light_internal_radius_range=(0.05, 0.1),
        reflected_light_external_radius_range=(0.20, 0.40),
    )
    return result, {}


def _apply_shadow_cast(img):
    """Gentle, realistic shadow falling across the document."""
    opacity = round(random.uniform(0.2, 0.4), 2)
    result = _safe_augraphy(
        ShadowCast, img,
        shadow_side="random",
        shadow_vertices_range=(2, 4),
        shadow_width_range=(0.3, 0.5),
        shadow_height_range=(0.3, 0.5),
        shadow_color=(0, 0, 0),
        shadow_opacity_range=(opacity, min(opacity + 0.05, 0.5)),
    )
    return result, {"opacity": opacity}


def _apply_watermark(img):
    """Faded, low-contrast watermark text overlay."""
    result = _safe_augraphy(
        WaterMark, img,
        watermark_word="random",
        watermark_font_size=(40, 80),
        watermark_font_thickness=(3, 6),
        watermark_rotation=(-45, 45),
        watermark_location="random",
        watermark_color='random',
        watermark_method="darken",
    )
    return result, {}


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
    """Rotate a bounding box by applying affine matrix M to its 4 corners,
    then take the axis-aligned bounding box of the result.

    Returns the modified block dict, or None if the rotated box is too
    small (< 5 px in either dimension) to be useful.
    """
    x1 = block[coord_keys[0]]
    y1 = block[coord_keys[1]]
    x2 = block[coord_keys[2]]
    y2 = block[coord_keys[3]]

    # 4 corners of the original bbox
    corners = np.array([
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2],
    ], dtype=np.float64)

    # Apply the 2×3 affine matrix: [new_x, new_y] = M @ [x, y, 1]^T
    ones = np.ones((4, 1), dtype=np.float64)
    corners_h = np.hstack([corners, ones])
    transformed = (M @ corners_h.T).T  # shape (4, 2)

    # Axis-aligned bounding box of the 4 transformed corners, clamped
    rx1 = max(0, int(round(transformed[:, 0].min())))
    ry1 = max(0, int(round(transformed[:, 1].min())))
    rx2 = min(new_w, int(round(transformed[:, 0].max())))
    ry2 = min(new_h, int(round(transformed[:, 1].max())))

    # Discard degenerate boxes
    if rx2 <= rx1 + 5 or ry2 <= ry1 + 5:
        return None

    block[coord_keys[0]] = rx1
    block[coord_keys[1]] = ry1
    block[coord_keys[2]] = rx2
    block[coord_keys[3]] = ry2
    return block


def transform_annotation(name, annotation, params, old_shape, new_shape):
    """Return an updated copy of the annotation dict.

    For the 9 augmentations that preserve dimensions, this is a simple
    deep-copy with an added ``meta.augmentation`` field.

    For *rotation* (the only dimension-changing augmentation), every block
    and image entry has its bounding-box coordinates rotated through the
    same affine matrix that was applied to the pixels.
    """
    ann = copy.deepcopy(annotation)

    # Always record which augmentation was applied
    if "meta" not in ann:
        ann["meta"] = {}
    # Strip internal params (prefixed with _) from the public record
    public_params = {k: v for k, v in params.items() if not k.startswith("_")}
    ann["meta"]["augmentation"] = {"name": name, **public_params}

    if name != "rotation":
        # No coordinate changes needed
        return ann

    # ---- Rotation-specific coordinate updates ----
    M = params["_matrix"]
    new_w, new_h = params["_new_size"]

    # Update canvas dimensions
    ann["dimensions"]["width"] = new_w
    ann["dimensions"]["height"] = new_h

    # Transform block bounding boxes
    coord_keys = ("top_left_x", "top_left_y", "bottom_right_x", "bottom_right_y")

    updated_blocks = []
    for block in ann.get("blocks", []):
        result = _rotate_bbox(block, M, new_w, new_h, coord_keys)
        if result is not None:
            updated_blocks.append(result)
    ann["blocks"] = updated_blocks

    # Transform image entry bounding boxes
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

    Returns True on success, False on any failure (the caller should
    continue regardless).
    """
    img = cv2.imread(img_path)
    if img is None:
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            annotation = json.load(f)
    except Exception:
        return False

    try:
        augmented_img, params = apply_augmentation(aug_name, img)
    except Exception as e:
        print(f"  [aug] '{aug_name}' failed on {img_path}: {e}")
        return False

    if augmented_img is None or augmented_img.size == 0:
        return False

    new_annotation = transform_annotation(
        aug_name, annotation, params, img.shape, augmented_img.shape
    )

    cv2.imwrite(out_img_path, augmented_img)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(new_annotation, f, ensure_ascii=False, indent=4)

    return True
