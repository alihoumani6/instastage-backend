# main.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from utils.storage import get_storage
from PIL import Image
import io, uuid, os
from urllib.parse import urljoin

app = FastAPI()
storage = get_storage()

def make_public_url(request: Request, url_or_path: str) -> str:
    """
    Ensures the client gets a fully-qualified HTTPS URL.
    - If storage returned an absolute http(s) URL, return it unchanged.
    - If storage returned a relative path (e.g. 'media/...' or '/media/...'),
      build it against PUBLIC_BASE_URL (if set) or the incoming request's base URL.
    """
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        return url_or_path

    base = os.environ.get("PUBLIC_BASE_URL")
    if not base:
        # Render sets X-Forwarded-* so request.base_url is already public (https)
        base = str(request.base_url)
    if not base.endswith("/"):
        base += "/"

    path = url_or_path[1:] if url_or_path.startswith("/") else url_or_path
    return urljoin(base, path)

@app.post("/stage")
async def stage(
    request: Request,
    image: UploadFile = File(...),
    room_type: str = Form(...),
    furniture_style: str = Form(...),
    tier: str = Form(...),
):
    try:
        raw = await image.read()

        # Save original (normalize to high-quality JPEG)
        job_id = str(uuid.uuid4())
        orig_key = f"originals/{job_id}.jpg"

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95, optimize=True)
        orig_bytes = buf.getvalue()

        original_url_raw = storage.save_bytes(orig_key, orig_bytes, "image/jpeg")

        # Run staging pipeline -> returns a PIL.Image
        from staging.pipeline import stage_image_async
        staged_pil = await stage_image_async(img, room_type, furniture_style, None)

        # Encode staged -> JPEG and store
        sbuf = io.BytesIO()
        staged_pil.save(sbuf, format="JPEG", quality=95, optimize=True)
        staged_bytes = sbuf.getvalue()

        staged_key = f"staged/{job_id}_staged.jpg"
        staged_url_raw = storage.save_bytes(staged_key, staged_bytes, "image/jpeg")

        # Force absolute, public URLs for mobile clients
        original_url = make_public_url(request, original_url_raw)
        staged_url = make_public_url(request, staged_url_raw)

        return {
            "job_id": job_id,
            "room_type": room_type,
            "furniture_style": furniture_style,
            "tier": tier,
            "original_url": original_url,
            "staged_url": staged_url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI staging failed: {e}")
