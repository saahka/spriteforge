"""Post-processing that turns raw generations into actual game-ready assets."""
from __future__ import annotations

import colorsys
import io
import math
from collections import Counter
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# ---------------------------------------------------------------- palettes ---


def _build_palette(img: Image.Image, colors: int) -> list[tuple[int, int, int]]:
    """k-means-lite palette using Pillow's adaptive quantizer."""
    small = img.convert("RGB").resize((96, 96), Image.LANCZOS)
    pal_img = small.quantize(colors=max(2, min(64, colors)), method=Image.MEDIANCUT)
    palette = pal_img.getpalette() or []
    used = pal_img.getcolors() or []
    colors_used = sorted(used, key=lambda c: -c[0])
    out: list[tuple[int, int, int]] = []
    for _count, idx in colors_used:
        base = idx * 3
        if base + 2 < len(palette):
            out.append((palette[base], palette[base + 1], palette[base + 2]))
    return out or [(0, 0, 0), (255, 255, 255)]


def apply_palette(img: Image.Image, colors: int = 32, dither: bool = True) -> Image.Image:
    """Quantize to a fixed palette, keeping alpha intact."""
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    rgb = img.convert("RGB")
    if dither:
        rgb = rgb.convert("P", palette=Image.ADAPTIVE, colors=colors, dither=Image.FLOYDSTEINBERG)
        rgb = rgb.convert("RGB")
    else:
        rgb = rgb.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    if alpha is not None:
        out = rgb.convert("RGBA")
        out.putalpha(alpha)
        return out
    return rgb


def _hsv(h: int, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h / 255.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


# --------------------------------------------------------------- pixel art ---


def pixelate(
    img: Image.Image,
    target: int = 128,
    mode: str = "reduce",
    palette: int | None = None,
) -> Image.Image:
    """Downscale then upscale with NEAREST to get real, hard pixel edges.

    `target` is the short-side pixel count, e.g. 64 gives a 64px-tall sprite.
    """
    w, h = img.size
    short = min(w, h)
    target = max(8, min(1024, int(target)))
    scale = max(1, round(short / target))
    small_w = max(1, w // scale)
    small_h = max(1, h // scale)

    if mode == "ordered":
        small = _ordered_dither(img.resize((small_w, small_h), Image.BOX), levels=2)
    else:
        small = img.resize((small_w, small_h), Image.BOX)
    if palette:
        small = apply_palette(small, palette)
    return small.resize((w, h), Image.NEAREST)


def _ordered_dither(img: Image.Image, levels: int = 2) -> Image.Image:
    """4x4 Bayer thresholding — gives that hand-pixelated look."""
    arr = np.asarray(img.convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    bayer = np.array(
        [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32
    )
    tile = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w]
    step = 255.0 / max(1, levels - 1)
    arr = np.floor(arr / step + tile / 16.0) * step
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def upscale(img: Image.Image, factor: int = 2) -> Image.Image:
    factor = max(1, min(4, int(factor)))
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


# ----------------------------------------------------------------- cutout ---


def _edge_color_samples(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img.convert("RGB")).astype(np.float32)
    h, w, _ = arr.shape
    band = max(1, min(h, w) // 24)
    samples = np.concatenate(
        [
            arr[:band].reshape(-1, 3),
            arr[-band:].reshape(-1, 3),
            arr[:, :band].reshape(-1, 3),
            arr[:, -band:].reshape(-1, 3),
        ]
    )
    return samples


def _flood_background(arr: np.ndarray, tolerance: float) -> np.ndarray:
    """Mark background pixels by flood-filling inward from the border.

    Propagating from the edges handles textured/noisy backgrounds far better
    than a global colour-distance threshold, which breaks up as soon as the
    background is dithered or pixelated.
    """
    h, w, _ = arr.shape
    flat = arr.reshape(-1, 3)
    # Squared distance is enough; avoids a sqrt per neighbour comparison.
    tol2 = float(tolerance) ** 2

    visited = np.zeros(h * w, dtype=bool)
    stack: list[int] = []

    def push(idx: int) -> None:
        if not visited[idx]:
            visited[idx] = True
            stack.append(idx)

    for x in range(w):
        push(x)
        push((h - 1) * w + x)
    for y in range(h):
        push(y * w)
        push(y * w + w - 1)

    bg = np.zeros(h * w, dtype=bool)
    while stack:
        idx = stack.pop()
        bg[idx] = True
        y, x = divmod(idx, w)
        ref = flat[idx]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            nidx = ny * w + nx
            if visited[nidx]:
                continue
            if np.sum((flat[nidx] - ref) ** 2) <= tol2:
                push(nidx)
    return bg.reshape(h, w)


def remove_background_flood(
    img: Image.Image,
    tolerance: int = 42,
    soft: int = 18,
) -> Image.Image:
    """Background removal with a feathered alpha edge (no SciPy dependency)."""
    rgb = img.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32)
    bg = _flood_background(arr, tolerance)

    h, w = bg.shape
    # Iterative dilation: number of iterations = distance from the background.
    soft = int(max(0, min(64, soft)))
    alpha = np.where(bg, 0.0, 1.0).astype(np.float32)
    band = np.where(bg, 0.0, 1.0).astype(np.float32)
    for i in range(1, soft + 1):
        band = _dilate_band(band, h, w)
        t = i / (soft + 1)
        alpha = np.where(band > 0, np.maximum(alpha, t), alpha)

    if img.mode == "RGBA":
        existing = np.asarray(img.getchannel("A")).astype(np.float32) / 255.0
        alpha = alpha * existing
    out = rgb.convert("RGBA")
    out.putalpha(Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8), mode="L"))
    return out


def _dilate_band(band: np.ndarray, h: int, w: int) -> np.ndarray:
    """4-neighbour dilation on a float mask, clamped at the borders."""
    out = band.copy()
    out[1:, :] = np.maximum(out[1:, :], band[:-1, :])
    out[:-1, :] = np.maximum(out[:-1, :], band[1:, :])
    out[:, 1:] = np.maximum(out[:, 1:], band[:, :-1])
    out[:, :-1] = np.maximum(out[:, :-1], band[:, 1:])
    return out


def auto_cutout(img: Image.Image, tolerance: int = 42, soft: int = 18) -> Image.Image:
    """Remove the background and trim transparent borders."""
    cut = remove_background_flood(img, tolerance=tolerance, soft=soft)
    return trim(cut)


def trim(img: Image.Image, pad: int = 0) -> Image.Image:
    if img.mode != "RGBA":
        return img
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return img
    out = img.crop(bbox)
    if pad > 0:
        out = ImageOps.expand(out, border=pad, fill=(0, 0, 0, 0))
    return out


def largest_component(img: Image.Image, threshold: int = 16) -> Image.Image:
    """Keep only the biggest opaque blob, dropping stray specks."""
    if img.mode != "RGBA":
        return img
    arr = np.asarray(img)
    alpha = arr[:, :, 3]
    mask = alpha > threshold
    if not mask.any():
        return img
    # Flood fill from the border to find background, then invert.
    from collections import deque

    h, w = mask.shape
    bg = ~mask
    seen = np.zeros_like(bg)
    dq: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bg[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if bg[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and bg[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                dq.append((ny, nx))
    fg = mask & ~seen
    if not fg.any():
        return img
    out = arr.copy()
    out[:, :, 3] = np.where(fg, alpha, 0).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


# ----------------------------------------------------------------- tiles ----


def make_seamless(img: Image.Image, mode: str = "offset") -> Image.Image:
    """Make a texture tileable.

    `offset` rolls the image by half and cross-fades the seam, which is cheap
    and works well on generated textures.
    """
    img = img.convert("RGB")
    w, h = img.size
    if mode == "mirror":
        canvas = Image.new("RGB", (w, h))
        canvas.paste(img, (0, 0))
        half = img.crop((w // 2, 0, w, h)).transpose(Image.FLIP_LEFT_RIGHT)
        canvas.paste(half, (0, 0))
        return canvas

    arr = np.asarray(img).astype(np.float32)
    rolled = np.roll(np.roll(arr, h // 2, axis=0), w // 2, axis=1)
    out = arr.copy()
    # Feather the seam across a band around the midpoint.
    band = max(4, w // 6)
    for i in range(band):
        t = (i + 1) / (band + 1)
        a = int(h / 2 - band / 2 + i)
        b = (a + h // 2) % h
        out[a] = out[a] * (1 - t) + rolled[a] * t
        out[b] = out[b] * (1 - t) + rolled[b] * t
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


# ---------------------------------------------------------------- sprites ---


def split_sheet(
    img: Image.Image, cols: int = 4, rows: int = 4
) -> list[tuple[Image.Image, int, int]]:
    """Slice a grid sheet into frames. Returns (image, col, row)."""
    cols = max(1, min(16, int(cols)))
    rows = max(1, min(16, int(rows)))
    w, h = img.size
    fw = w // cols
    fh = h // rows
    if fw < 4 or fh < 4:
        return [(img, 0, 0)]
    frames: list[tuple[Image.Image, int, int]] = []
    for r in range(rows):
        for c in range(cols):
            frames.append((img.crop((c * fw, r * fh, (c + 1) * fw, (r + 1) * fh)), c, r))
    return frames


def trim_frames(
    frames: Sequence[tuple[Image.Image, int, int]], threshold: int = 12
) -> list[tuple[Image.Image, int, int]]:
    """Trim every frame to a shared bounding box so the animation stays aligned."""
    boxes = []
    for img, _c, _r in frames:
        if img.mode == "RGBA":
            a = img.getchannel("A")
            boxes.append(a.getbbox() or (0, 0, img.width, img.height))
        else:
            boxes.append((0, 0, img.width, img.height))
    if not boxes:
        return list(frames)
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    out = []
    for img, c, r in frames:
        out.append((img.crop((x0, y0, x1, y1)), c, r))
    return out


def contact_sheet(frames: Iterable[Image.Image], cols: int = 4) -> Image.Image:
    frames = list(frames)
    if not frames:
        raise ValueError("no frames")
    fw, fh = frames[0].size
    cols = max(1, min(cols, len(frames)))
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGBA", (fw * cols, fh * rows), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.alpha_composite(f.convert("RGBA"), ((i % cols) * fw, (i // cols) * fh))
    return sheet


# ----------------------------------------------------------------- atlas ----


def build_atlas(
    frames: Sequence[Image.Image], cols: int = 4, padding: int = 0
) -> tuple[Image.Image, dict]:
    """Pack frames into a grid atlas and return Aseprite-like JSON metadata."""
    frames = [f.convert("RGBA") for f in frames]
    if not frames:
        raise ValueError("no frames")
    fw, fh = frames[0].size
    cols = max(1, min(cols, len(frames)))
    rows = math.ceil(len(frames) / cols)
    step_x = fw + padding
    step_y = fh + padding
    atlas = Image.new("RGBA", (cols * step_x - padding, rows * step_y - padding), (0, 0, 0, 0))
    meta: dict = {
        "frame_width": fw,
        "frame_height": fh,
        "columns": cols,
        "rows": rows,
        "padding": padding,
        "frames": [],
    }
    for i, f in enumerate(frames):
        x = (i % cols) * step_x
        y = (i // cols) * step_y
        atlas.alpha_composite(f, (x, y))
        meta["frames"].append({"index": i, "x": x, "y": y, "w": fw, "h": fh})
    return atlas, meta


# ----------------------------------------------------------------- io -------


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_webp_bytes(img: Image.Image, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=5)
    return buf.getvalue()


def thumbnail(img: Image.Image, size: int = 384) -> Image.Image:
    # Image.thumbnail() resizes in place and returns None, so work on a copy.
    out = img.copy()
    out.thumbnail((size, size), Image.LANCZOS)
    return out


def dominant_colors(img: Image.Image, count: int = 5) -> list[str]:
    small = img.convert("RGB").resize((64, 64), Image.NEAREST)
    counter = Counter(small.getdata())
    total = sum(counter.values()) or 1
    out = []
    for color, n in counter.most_common(count):
        r, g, b = color
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        # Boost saturation/brightness a bit so the swatch reads well in the UI.
        s = min(1.0, s * 1.25)
        v = min(1.0, max(v, 0.35))
        rr, gg, bb = _hsv(int(h * 255), s, v)
        weight = n / total
        out.append(f"#{rr:02x}{gg:02x}{bb:02x}")
    return out


def enhance_for_game(img: Image.Image, contrast: float = 1.08, saturation: float = 1.1) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Color(img).enhance(saturation)
    return img


# Steps must run in a fixed order regardless of how the user listed them:
# cutout before pixelation (pixelation shreds a flat background into noise),
# palette last so quantisation cannot re-introduce background-coloured pixels.
POST_ORDER = ("cutout", "seamless", "pixelate", "palette", "upscale", "split")


def order_steps(steps: Sequence[str]) -> list[str]:
    known = [s for s in POST_ORDER if s in steps]
    unknown = [s for s in steps if s not in POST_ORDER]
    return known + unknown


def postprocess(
    img: Image.Image,
    steps: Sequence[str],
    *,
    pixel_size: int = 64,
    palette_colors: int = 16,
    tolerance: int = 42,
    soft: int = 18,
    sheet_cols: int = 4,
    sheet_rows: int = 4,
) -> tuple[Image.Image, list[Image.Image]]:
    """Apply the post-processing chain. Returns (main image, extra frames)."""
    frames: list[Image.Image] = []
    out = img
    for step in order_steps(steps):
        if step == "cutout":
            out = auto_cutout(out, tolerance=tolerance, soft=soft)
            out = largest_component(out)
        elif step == "pixelate":
            out = pixelate(out, target=pixel_size, palette=palette_colors)
        elif step == "palette":
            out = apply_palette(out, colors=palette_colors)
        elif step == "seamless":
            out = make_seamless(out)
        elif step == "upscale":
            out = upscale(out, 2)
        elif step == "split":
            cut = split_sheet(out, sheet_cols, sheet_rows)
            cut = trim_frames(cut)
            frames = [f for f, _c, _r in cut]
    return out, frames
