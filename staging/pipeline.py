# staging/pipeline.py
from typing import Optional
from PIL import Image, ImageChops, ImageFilter, ImageOps

from .generator_edit import edit_add_furniture  # calls OpenAI Images Edit


def _normalize_room(room_type: str) -> str:
    rt = (room_type or "").strip().lower()
    mapping = {
        "living room": "Living room", "living": "Living room",
        "bedroom": "Bedroom",
        "dining room": "Dining room", "dining": "Dining room",
        "home office": "Home office", "office": "Home office",
        "kids room": "Kids room", "kids": "Kids room",
        "kitchen": "Kitchen",
        "bathroom": "Bathroom", "bath": "Bathroom",
    }
    return mapping.get(rt, "Living room")


def _stable_change_mask(
    original: Image.Image,
    edited: Image.Image,
    thr: int = 16,       # base threshold for "real" change (lower = more sensitive)
    grow_px: int = 3,    # dilate a bit more to include furniture edges
    blur_px: float = 2.0 # feather to avoid seams
) -> Image.Image:
    """
    Build a robust, feathered alpha where furniture changed the image.
    Returns 8-bit 'L' (0=keep original, 255=use edited).
    """
    if original.mode != "RGB":
        original = original.convert("RGB")
    if edited.mode != "RGB":
        edited = edited.convert("RGB")

    # Core difference and light denoise
    diff = ImageChops.difference(original, edited).convert("L")
    diff = ImageOps.autocontrast(diff, cutoff=1)

    # Pre-blur slightly so thresholding doesn’t produce 1-pixel bands
    diff = diff.filter(ImageFilter.GaussianBlur(radius=0.8))

    # Hard-ish threshold -> binary regions of true change
    mask = diff.point(lambda p: 255 if p > thr else 0).convert("L")

    # Morphological grow to capture anti-aliased edges
    for _ in range(max(0, grow_px)):
        mask = mask.filter(ImageFilter.MaxFilter(3))

    # Feather (soft edge = no seam)
    if blur_px > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_px))

    # Gentle curve (avoid super-hard 0/255 steps that cause lines)
    mask = mask.point(lambda a: int(a * 0.92))

    # Anti-seam polish: remove sub-pixel rows/columns that are too thin/too faint
    # Min then blur brings tiny bright lines back down before the final paste.
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.6))

    return mask


async def stage_image_async(
    base: Image.Image,
    room_type: str,
    style: str,
    floor_y_override: Optional[int] = None,  # kept for signature compat; unused here
) -> Image.Image:
    """
    Furniture-only compositing:
      1) Let the model stage freely (we filter afterward).
      2) Compute a robust, feathered change-mask.
      3) Paste ONLY changed pixels over the original (floors/walls/ceiling preserved).
    """
    room = _normalize_room(room_type)

    # 1) Ask the model to add furniture (no mask limits; we’ll filter)
    edited = await edit_add_furniture(
        base_image=base,
        room_type=room,
        furniture_style=style,
        rgba_mask=None,
    )

    # 2) Size guard
    if edited.size != base.size:
        edited = edited.resize(base.size, Image.LANCZOS)

    # 3) Build stable mask (this is where the seam fix happens)
    alpha = _stable_change_mask(
        original=base,
        edited=edited,
        thr=16,
        grow_px=3,
        blur_px=2.0
    )

    # 4) Composite
    out = base.convert("RGB").copy()
    out.paste(edited.convert("RGB"), (0, 0), alpha)
    return out
