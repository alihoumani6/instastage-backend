# utils/watermark.py
from PIL import Image, ImageDraw, ImageFont

def add_watermark(img: Image.Image, text: str = "instastage") -> Image.Image:
    """
    Adds a centered semi-transparent watermark to an image.
    Returns a new Image (does not modify the original).
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Create transparent overlay
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Choose font
    try:
        font = ImageFont.truetype("arial.ttf", int(img.size[1] * 0.05))
    except Exception:
        font = ImageFont.load_default()

    # Get text size
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    # Center text at bottom
    x = (img.size[0] - text_w) / 2
    y = img.size[1] - text_h - (img.size[1] * 0.04)

    # Draw semi-transparent text (white with black shadow)
    shadow_offset = int(font.size * 0.05)
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=(0, 0, 0, 120))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 160))

    # Blend overlay
    out = Image.alpha_composite(img, overlay)
    return out.convert("RGB")
