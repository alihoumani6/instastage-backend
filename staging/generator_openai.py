# staging/generator_openai.py
import os
import base64
import httpx
import io
from typing import Dict, Any
from PIL import Image
import numpy as np
import cv2
from rembg import remove as rembg_remove

IMAGES_URL = "https://api.openai.com/v1/images/generations"

STYLE_HINTS = {
    "Modern": "modern, clean lines, neutral fabrics, matte finishes",
    "Scandinavian": "light wood, airy, cozy, natural textures",
    "Industrial": "metal + wood mix, darker tones, rugged",
    "Midcentury": "walnut, tapered legs, retro silhouettes",
    "Luxury": "plush upholstery, metallic accents, refined",
    "Coastal": "light linens, rattan, pale blues",
    "Farmhouse": "wood textures, warm neutrals, casual",
    "Standard": "tasteful, neutral palette",
}

def _get_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return key

def _get_headers() -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {_get_key()}"}
    proj = os.getenv("OPENAI_PROJECT", "").strip()
    if proj:
        headers["OpenAI-Project"] = proj
    return headers

def _prompt(item: str, style: str) -> str:
    style_bits = STYLE_HINTS.get(style, style)
    # HARD constraints to prevent mini-room “frames”
    return (
        f"A single {style} style ({style_bits}) {item} — "
        f"studio catalog photo on plain seamless white background, no walls, no floor, no frame, "
        f"no scene, no shadow, no people, full object visible, correct proportions. "
        f"High fidelity textures. Output should be ideal for background removal."
    )

async def _decode_image_response(data: Dict[str, Any]) -> bytes:
    item = data["data"][0]
    b64 = item.get("b64_json")
    if b64:
        return base64.b64decode(b64)
    url = item.get("url")
    if not url:
        raise RuntimeError(f"Images API returned no image data: {data}")
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content

def _ensure_rgba(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")

def _matte_if_needed(img_rgba: Image.Image) -> Image.Image:
    """
    If the returned image still has a scene/white background, remove it with rembg.
    """
    # If there is already transparency, keep it; otherwise remove bg.
    arr = np.array(img_rgba)
    has_alpha_holes = arr.shape[2] == 4 and np.any(arr[:, :, 3] < 255)
    if has_alpha_holes:
        return img_rgba
    # rembg expects bytes
    buf = io.BytesIO()
    img_rgba.save(buf, "PNG")
    cut = rembg_remove(buf.getvalue())
    return Image.open(io.BytesIO(cut)).convert("RGBA")

def _pick_size_for_model(model: str, base_width_px: int) -> str:
    # Allowed sizes
    if model == "dall-e-3":
        return "1024x1024"
    return "1536x1024" if base_width_px >= 1400 else "1024x1024"

async def _call_images(model: str, prompt: str, size: str) -> bytes:
    headers = _get_headers()
    payload = {"model": model, "prompt": prompt, "size": size}
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(IMAGES_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI Images error {resp.status_code}: {resp.text[:800]}")
        data = resp.json()
    return await _decode_image_response(data)

async def generate_openai_png(item: str, style: str, base_width_px: int) -> bytes:
    """
    Generate a transparent PNG cutout. Tries gpt-image-1; falls back to dall-e-3.
    Always post-process with rembg to guarantee a clean cutout.
    """
    prompt = _prompt(item, style)
    # 1) Try gpt-image-1
    try:
        size = _pick_size_for_model("gpt-image-1", base_width_px)
        raw = await _call_images("gpt-image-1", prompt, size)
        img = _ensure_rgba(raw)
        img = _matte_if_needed(img)
    except RuntimeError as e:
        msg = str(e)
        if "403" in msg or "must be verified" in msg or "invalid_request" in msg or "model_not_found" in msg:
            # 2) Fallback to dall-e-3
            size = _pick_size_for_model("dall-e-3", base_width_px)
            raw = await _call_images("dall-e-3", prompt, size)
            img = _ensure_rgba(raw)
            img = _matte_if_needed(img)
        else:
            raise

    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()
