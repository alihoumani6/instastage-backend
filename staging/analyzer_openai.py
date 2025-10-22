# staging/analyzer_openai.py
import os, httpx, json, re
from typing import Optional, Dict, Any

RESPONSES_URL = "https://api.openai.com/v1/responses"

def _headers() -> Dict[str, str]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    proj = os.getenv("OPENAI_PROJECT", "").strip()
    if proj:
        h["OpenAI-Project"] = proj
    return h

def _coerce_room(s: str) -> str:
    s = s.lower()
    for opt in ["living room","bedroom","kitchen","bathroom","home office","dining room","kids room"]:
        if opt in s:
            return opt.title()
    return "Living room"

async def analyze_room_with_openai(image_url: str) -> Optional[Dict[str, Any]]:
    """
    Ask a vision model to return a tiny JSON blob:
      - room_type: one of target labels
      - floor_y_frac: float 0..1 (0 top, 1 bottom)
    We give the URL to the saved original image.
    """
    model = os.getenv("OPENAI_RESPONSES_MODEL", "gpt-4.1-mini")
    prompt = (
        "You are analyzing a real-estate interior photo. "
        "Classify the room type into exactly one of: "
        "[Living room, Bedroom, Kitchen, Bathroom, Home office, Dining room, Kids room]. "
        "Also estimate where the visible floor meets the back wall in the image as a fraction "
        "of image height (0 = top, 1 = bottom). Return strictly valid JSON: "
        "{\"room_type\":\"<label>\",\"floor_y_frac\":<number between 0.5 and 0.95>}."
    )
    payload = {
        "model": model,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": image_url},
            ],
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(RESPONSES_URL, headers=_headers(), json=payload)
            if r.status_code != 200:
                return None
            data = r.json()
    except Exception:
        return None

    # Extract the LLM's text output, then parse JSON
    text = ""
    out = data.get("output") or data.get("choices") or []
    if isinstance(out, list):
        for block in out:
            if isinstance(block, dict):
                # common shapes: {"type":"message","content":[{"type":"output_text","text":"..."}]}
                content = block.get("content")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") in ("output_text","text"):
                            text += item.get("text","")
    if not text:
        # Fallback: some responses have top-level "content"
        text = json.dumps(data)[:200]

    # Pull JSON object from text
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        room = _coerce_room(obj.get("room_type",""))
        fy = float(obj.get("floor_y_frac", 0.8))
        fy = max(0.5, min(0.95, fy))
        return {"room_type": room, "floor_y_frac": fy}
    except Exception:
        return None
