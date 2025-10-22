# staging/generator_edit.py
import os
import io
import base64
import requests
from typing import Optional
from PIL import Image

# No env checks at import. We'll check at call time.
API_URL = "https://api.openai.com/v1/images/edits"


def _ensure_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return key


def _to_jpeg_bytes(img: Image.Image, q: int = 92) -> bytes:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q, optimize=True)
    return buf.getvalue()


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def edit_add_furniture(
    base_image: Image.Image,
    room_type: str,
    furniture_style: str,
    rgba_mask: Optional[Image.Image] = None,  # If None, allow full-scene edit
) -> Image.Image:
    """
    Calls OpenAI Images Edit. If rgba_mask is provided, its transparent regions are editable.
    We keep the prompt very explicit about not altering existing surfaces,
    but the final 'furniture-only' compositing is enforced in pipeline.py.
    """
    key = _ensure_key()

    prompt = (
        f"Virtually stage this {room_type.lower()} by ADDING only {furniture_style.lower()} furniture and decor. "
        f"DO NOT modify existing walls, windows, doors, flooring, paint, trim, fireplace, or built-ins. "
        f"Respect camera perspective and lighting; add subtle object shadows on the floor if needed, "
        f"but avoid global color/contrast changes. Keep the composition authentic and photorealistic."
    )

    img_bytes = _to_jpeg_bytes(base_image)
    files = {"image": ("input.jpg", img_bytes, "image/jpeg")}

    # If a mask is provided, send it (transparent = editable).
    if rgba_mask is not None:
        files["mask"] = ("mask.png", _to_png_bytes(rgba_mask), "image/png")

    data = {
        "model": "gpt-image-1",
        "prompt": prompt,
        # We omit 'size' to avoid account/feature mismatches; pipeline resizes if needed.
        # "size": "auto",
    }
    headers = {"Authorization": f"Bearer {key}"}

    r = requests.post(API_URL, headers=headers, data=data, files=files, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI Image Edit error {r.status_code}: {r.text[:800]}")

    b64 = r.json()["data"][0]["b64_json"]
    out = Image.open(io.BytesIO(base64.b64decode(b64)))
    # Normalize to RGB for compositing
    return out.convert("RGB")
