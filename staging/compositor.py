# staging/compositor.py
from PIL import Image, ImageFilter, ImageStat, ImageEnhance
import io, os
from typing import Tuple, Dict, Optional

def _bytes_to_img(b: bytes) -> Image.Image:
    return Image.open(io.BytesIO(b)).convert("RGBA")

def _clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))

def _fit_to_width(img: Image.Image, target_w: int) -> Image.Image:
    if target_w <= 0: return img
    w, h = img.size
    if w <= 0: return img
    scale = target_w / float(w)
    return img.resize((max(1, int(round(w*scale))), max(1, int(round(h*scale)))), Image.LANCZOS)

def _shadow_under(layer: Image.Image, blur: int = 18, opacity: int = 90, y_scale: float = 0.25) -> Image.Image:
    alpha = layer.split()[-1]
    sh = Image.new("L", layer.size, 0)
    sh.paste(alpha, (0, 0))
    w, h = sh.size
    squeezed = sh.resize((w, max(1, int(h * y_scale))), Image.BILINEAR).filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.new("L", (w, h), 0)
    canvas.paste(squeezed, (0, h - squeezed.size[1]))
    rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rgba.putalpha(canvas.point(lambda v: int(v * (opacity / 255.0))))
    return rgba

def _avg_brightness(img: Image.Image) -> float:
    from PIL import ImageStat
    return float(ImageStat.Stat(img.convert("L")).mean[0])

def _match_tone(base_rgb: Image.Image, cutout_rgba: Image.Image) -> Image.Image:
    base_b = _avg_brightness(base_rgb)
    cut_b  = _avg_brightness(cutout_rgba)
    if cut_b <= 0: return cutout_rgba
    target = max(60.0, min(190.0, base_b))
    factor = max(0.7, min(1.3, target / cut_b))
    out = ImageEnhance.Brightness(cutout_rgba).enhance(factor)
    out = ImageEnhance.Contrast(out).enhance(1.04)
    return out

def _layout_specs(room_type: str, W: int, H: int, floor_y: Optional[int]) -> Dict[str, float]:
    rt = (room_type or "").lower()
    fy = int(H * 0.74) if floor_y is None else int(floor_y)

    main_w_scale_hint = float(os.getenv("INSTASTAGE_MAIN_W_SCALE", "0.48"))
    spec = {
        "floor_y": fy,
        "rug_w":   0.78,
        "main_w":  main_w_scale_hint,
        "aux_w":   0.26,
        "rug_y":   0,
        "main_y":  0,
        "aux_y":   -6,
        "shadow": {
            "rug":  (16, 70, 0.18),
            "aux":  (18, 80, 0.22),
            "main": (22, 92, 0.26),
        },
        "depth": ["rug","aux","main"],
    }
    if "bed" in rt:
        spec.update({"rug_w": 0.86, "main_w": max(0.58, main_w_scale_hint), "aux_w": 0.24, "aux_y": -4})
    elif "dining" in rt:
        spec.update({"rug_w": 0.84, "main_w": max(0.52, main_w_scale_hint), "aux_w": 0.24})
    elif "office" in rt:
        spec.update({"rug_w": 0.68, "main_w": max(0.50, main_w_scale_hint), "aux_w": 0.24})
    elif "kids" in rt:
        spec.update({"rug_w": 0.78, "main_w": max(0.52, main_w_scale_hint), "aux_w": 0.28})
    elif "kitchen" in rt:
        spec.update({"rug_w": 0.58, "main_w": max(0.44, main_w_scale_hint), "aux_w": 0.22})
    elif "bath" in rt:
        spec.update({"rug_w": 0.52, "main_w": max(0.36, main_w_scale_hint), "aux_w": 0.18})
    for k in ("rug_w","main_w","aux_w"):
        spec[k] = float(max(0.18, min(0.92, spec[k])))
    return spec

def composite_scene_room_aware(
    base_rgb: Image.Image,
    room_type: str,
    primary_png: bytes,
    rug_png: bytes,
    aux_png: bytes,
    floor_y_override: Optional[int] = None,
) -> Image.Image:
    base = base_rgb.convert("RGBA")
    W, H = base.size
    spec = _layout_specs(room_type, W, H, floor_y_override)

    prim = _match_tone(base_rgb, _bytes_to_img(primary_png))
    rug  = _match_tone(base_rgb, _bytes_to_img(rug_png))
    aux  = _match_tone(base_rgb, _bytes_to_img(aux_png))

    rug  = _fit_to_width(rug,  int(W * spec["rug_w"]))
    prim = _fit_to_width(prim, int(W * spec["main_w"]))
    aux  = _fit_to_width(aux,  int(W * spec["aux_w"]))

    floor_y = spec["floor_y"]

    # Optional obstacle-aware x center injected by pipeline
    x_center_hint = os.getenv("INSTASTAGE_MAIN_XCENTER")
    def place(layer: Image.Image, y_offset: int = 0, use_hint: bool = False) -> Tuple[int, int]:
        w, h = layer.size
        if use_hint and x_center_hint is not None:
            xc = int(x_center_hint)
            x = int(xc - w / 2)
        else:
            x = (W - w) // 2
        y = floor_y - h + y_offset
        return _clamp(x, 0, max(0, W - w)), _clamp(y, 0, max(0, H - h))

    rug_pos   = place(rug,  spec["rug_y"],  use_hint=False)
    aux_pos   = place(aux,  spec["aux_y"],  use_hint=False)
    main_pos  = place(prim, spec["main_y"], use_hint=True)   # main piece avoids obstacles

    canvas = base.copy()
    br, or_, yr = spec["shadow"]["rug"]
    bt, ot, yt = spec["shadow"]["aux"]
    bm, om, ym = spec["shadow"]["main"]

    for layer_name in spec["depth"]:
        if layer_name == "rug":
            sh = _shadow_under(rug,  blur=br, opacity=or_, y_scale=yr)
            canvas.alpha_composite(sh, rug_pos)
            canvas.alpha_composite(rug, rug_pos)
        elif layer_name == "aux":
            sh = _shadow_under(aux,  blur=bt, opacity=ot, y_scale=yt)
            canvas.alpha_composite(sh, aux_pos)
            canvas.alpha_composite(aux, aux_pos)
        elif layer_name == "main":
            sh = _shadow_under(prim, blur=bm, opacity=om, y_scale=ym)
            canvas.alpha_composite(sh, main_pos)
            canvas.alpha_composite(prim, main_pos)

    return canvas.convert("RGB")
