import os
import uuid
from datetime import datetime
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from PIL import Image, ImageDraw, ImageFont

# ---------- Config ----------
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")  # change if deploying
MEDIA_DIR = "media"
ORIG_DIR = os.path.join(MEDIA_DIR, "originals")
STAGED_DIR = os.path.join(MEDIA_DIR, "staged")

os.makedirs(ORIG_DIR, exist_ok=True)
os.makedirs(STAGED_DIR, exist_ok=True)

app = FastAPI(title="InstaStaged Backend", version="0.1")

# CORS so your iOS app / local tools can hit it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOM_TYPES = {
    "Bedroom", "Living room", "Kitchen", "Bathroom",
    "Home office", "Dining room", "Kids room"
}
STYLES = {
    "Modern", "Standard", "Scandinavian", "Industrial",
    "Midcentury", "Luxury", "Coastal", "Farmhouse"
}

# ---------- Helpers ----------

def save_upload(file: UploadFile, dest_path: str) -> None:
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

def add_watermark(img: Image.Image, text="instastaged") -> Image.Image:
    """Non-destructive: this works on a copy of the staged result only."""
    im = img.copy().convert("RGBA")
    w, h = im.size
    overlay = Image.new("RGBA", im.size, (0,0,0,0))
    draw = ImageDraw.Draw(overlay)

    # font sizing relative to width
    font_size = max(18, int(w * 0.045))
    try:
        font = ImageFont.truetype("Arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    text = text.lower()
    tw, th = draw.textbbox((0,0), text, font=font)[2:]
    margin = int(w * 0.04)
    x = w - tw - margin
    y = h - th - margin

    draw.text((x, y), text, fill=(255,255,255,180), font=font)
    composed = Image.alpha_composite(im, overlay)
    return composed.convert("RGB")

# ---------- Routes ----------

@app.get("/")
def root():
    return {"ok": True, "service": "InstaStaged Backend", "time": datetime.utcnow().isoformat()}

@app.post("/stage")
async def stage_photo(
    image: UploadFile = File(...),
    room_type: str = Form(...),
    furniture_style: str = Form(...),
    tier: str = Form("free")  # "free" or "pro"
):
    # Validate inputs
    if room_type not in ROOM_TYPES:
        raise HTTPException(400, f"Invalid room_type: {room_type}")
    if furniture_style not in STYLES:
        raise HTTPException(400, f"Invalid furniture_style: {furniture_style}")
    if tier not in {"free", "pro"}:
        raise HTTPException(400, f"Invalid tier: {tier}")

    # Generate IDs / paths
    job_id = str(uuid.uuid4())
    orig_name = f"{job_id}.jpg"
    staged_name = f"{job_id}_staged.jpg"
    orig_path = os.path.join(ORIG_DIR, orig_name)
    staged_path = os.path.join(STAGED_DIR, staged_name)

    # Save original (immutable)
    save_upload(image, orig_path)

    # Load original for staging
    try:
        base = Image.open(orig_path).convert("RGB")
    except Exception:
        raise HTTPException(400, "Unsupported image format")

    # --------- TODO: AI Staging ----------
    # This is where you'll:
    # 1) Analyze room & create placement mask (read-only on base)
    # 2) Generate transparent PNG furniture layers (style-aware)
    # 3) Warp + composite layers over 'base' WITHOUT altering base pixels
    #
    # For now: just copy base to simulate a staged result.
    staged = base.copy()

    # Free tier: watermark staged copy only
    if tier == "free":
        staged = add_watermark(staged, "instastaged")

    # Save staged output
    staged.save(staged_path, "JPEG", quality=92)

    # Return URLs to fetch images
    return JSONResponse({
        "job_id": job_id,
        "room_type": room_type,
        "furniture_style": furniture_style,
        "tier": tier,
        "original_url": f"{BASE_URL}/media/originals/{orig_name}",
        "staged_url": f"{BASE_URL}/media/staged/{staged_name}",
    })

# Static file serving (dev convenience)
@app.get("/media/originals/{filename}")
def get_original(filename: str):
    path = os.path.join(ORIG_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path)

@app.get("/media/staged/{filename}")
def get_staged(filename: str):
    path = os.path.join(STAGED_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path)
