# staging/compositor.py
from PIL import Image, ImageFilter
import io

def _bytes_to_img(b: bytes) -> Image.Image:
    return Image.open(io.BytesIO(b)).convert("RGBA")

def _shadow_under(layer: Image.Image, blur: int = 18, opacity: int = 80, y_scale: float = 0.35) -> Image.Image:
    alpha = layer.split()[-1]
    sh = Image.new("L", layer.size, 0)
    sh.paste(alpha, (0,0))
    w, h = sh.size
    # squash to simulate floor contact
    sh = sh.resize((w, max(1, int(h * y_scale))), Image.BILINEAR).filter(ImageFilter.GaussianBlur(blur))
    pad = Image.new("L", (w, h), 0)
    pad.paste(sh, (0, h - sh.size[1]))
    rgba = Image.new("RGBA", (w, h), (0,0,0,0))
    rgba.putalpha(pad.point(lambda v: min(255, int(v * (opacity/255.0)))))
    return rgba

def composite_scene(base_rgb: Image.Image, rug_png: bytes, sofa_png: bytes, table_png: bytes) -> Image.Image:
    base = base_rgb.convert("RGBA")
    W, H = base.size
    rug   = _bytes_to_img(rug_png)
    sofa  = _bytes_to_img(sofa_png)
    table = _bytes_to_img(table_png)

    # Simple placements (centered, near lower third)
    rug_x = (W - rug.width)//2
    rug_y = int(H * 0.68)

    sofa_x = (W - sofa.width)//2
    sofa_y = rug_y - int(sofa.height * 0.78)

    table_x = (W - table.width)//2
    table_y = rug_y + int(rug.height * 0.12) - int(table.height * 0.58)

    canvas = base.copy()

    for lay, (x,y), blur, opac, ys in [
        (rug,   (rug_x,   rug_y),   16, 70, 0.22),
        (table, (table_x, table_y), 14, 85, 0.20),
        (sofa,  (sofa_x,  sofa_y),  22, 90, 0.28),
    ]:
        sh = _shadow_under(lay, blur=blur, opacity=opac, y_scale=ys)
        canvas.alpha_composite(sh, (x, y))
        canvas.alpha_composite(lay, (x, y))

    return canvas.convert("RGB")
