#!/usr/bin/env python3
"""Python port of the core One Last Image workflow.

The browser version is mostly a deterministic image pipeline with a few UI-only
helpers. This module keeps the important processing steps:

1. Optional centered cover crop and zoom scaling
2. RGB to grayscale conversion
3. Optional pencil-texture shading for dark regions
4. Optional denoise pass
5. Line extraction via convolution kernels
6. Optional tone differencing between two kernels
7. Optional tone cut / posterization
8. Optional One Last Kiss style gradient alpha compositing
9. Optional watermark overlay
10. Optional comparison exports

Dependencies:
  pip install pillow numpy
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image


try:
    RESAMPLE_BILINEAR = Image.Resampling.BILINEAR
except AttributeError:  # Pillow < 9
    RESAMPLE_BILINEAR = Image.BILINEAR


@dataclass(frozen=True)
class Config:
    zoom: float = 1.0
    cover: bool = False
    light: float = 0.0
    shade_limit: int = 108
    shade_light: int = 80
    shade: bool = True
    kuma: bool = True
    hajimei: bool = False
    watermark: bool = True
    convolute_name: str = "一般"
    convolute1_diff: bool = True
    convolute_name2: Optional[str] = None
    light_cut: int = 128
    dark_cut: int = 118
    denoise: bool = True
    bevel_position: int = 20
    seed: Optional[int] = None


def average_kernel(size: int) -> np.ndarray:
    return np.full((size, size), 1.0 / (size * size), dtype=np.float32)


CONVOLUTES: dict[str, Optional[np.ndarray]] = {
    "精细": average_kernel(5),
    "一般": average_kernel(7),
    "稍粗": average_kernel(9),
    "超粗": average_kernel(11),
    "极粗": average_kernel(13),
    "浮雕": np.array(
        [
            1, 1, 1,
            1, 1, -1,
            -1, -1, -1,
        ],
        dtype=np.float32,
    ).reshape(3, 3),
    "线稿": None,
}


GRADIENT_STOPS = np.array([0.0, 0.4, 0.6, 0.7, 0.8, 1.0], dtype=np.float32)
GRADIENT_COLORS = np.array(
    [
        [251, 186, 48],
        [252, 114, 53],
        [252, 53, 78],
        [207, 54, 223],
        [55, 181, 217],
        [62, 182, 218],
    ],
    dtype=np.float32,
)


def script_root() -> Path:
    return Path(__file__).resolve().parent


def asset_path(name: str) -> Path:
    return script_root() / "html" / name


@lru_cache(maxsize=4)
def load_image(path: str) -> Image.Image:
    img = Image.open(path)
    return img.convert("RGBA")


def open_source_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def centered_cover_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width == height:
        return image
    if width > height:
        left = (width - height) // 2
        return image.crop((left, 0, left + height, height))
    top = (height - width) // 2
    return image.crop((0, top, width, top + width))


def target_size(image: Image.Image, config: Config) -> tuple[int, int]:
    width, height = image.size
    if config.cover:
        short_side = min(width, height)
        target = max(1, round(short_side / config.zoom))
        if target > 1920:
            target = 1920
        return target, target

    target_width = max(1, round(width / config.zoom))
    target_height = max(1, round(height / config.zoom))
    if target_width > 1920:
        scale = 1920 / target_width
        target_width = 1920
        target_height = max(1, round(target_height * scale))
    return target_width, target_height


def resize_input(image: Image.Image, config: Config) -> Image.Image:
    if config.cover:
        image = centered_cover_crop(image)
    size = target_size(image, config)
    return image.resize(size, RESAMPLE_BILINEAR)


def rgba_to_gray(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image, dtype=np.float32)[..., :3]
    gray = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return np.floor(gray).astype(np.float32)


def convolve_gray(gray: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    if kernel.ndim != 2 or kernel.shape[0] != kernel.shape[1]:
        raise ValueError("kernel must be a square matrix")

    size = kernel.shape[0]
    pad = size // 2
    padded = np.pad(gray, pad_width=pad, mode="edge")
    windows = sliding_window_view(padded, (size, size))
    result = np.tensordot(windows, kernel, axes=((2, 3), (0, 1)))
    return result.astype(np.float32)


def build_shade_map(
    gray: np.ndarray,
    config: Config,
    rng: np.random.Generator,
) -> np.ndarray:
    height, width = gray.shape
    texture = load_image(str(asset_path("pencil-texture.jpg")))
    max_side = max(width, height)
    texture = texture.resize((max_side, max_side), RESAMPLE_BILINEAR)
    texture = texture.crop((0, 0, width, height))
    texture_arr = np.asarray(texture, dtype=np.uint8)

    mask = np.where(gray > config.shade_limit, 0, 255).astype(np.uint8)
    alpha = rng.integers(0, 255, size=(height, width), dtype=np.uint8)

    shade_rgba = np.stack(
        [
            mask,
            np.full_like(mask, 128),
            np.full_like(mask, 128),
            alpha,
        ],
        axis=-1,
    )
    shade_img = Image.fromarray(shade_rgba, mode="RGBA")

    down_size = (max(1, width // 4), max(1, height // 4))
    shade_img = shade_img.resize(down_size, RESAMPLE_BILINEAR)
    shade_img = shade_img.resize((width, height), RESAMPLE_BILINEAR)
    shade_arr = np.asarray(shade_img, dtype=np.uint8)

    shade = np.round(
        (255 - texture_arr[..., 0])
        / 255.0
        * shade_arr[..., 0]
        / 255.0
        * config.shade_light,
    )
    return shade.astype(np.float32)


def build_gradient_rgb(width: int, height: int) -> np.ndarray:
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)
    t = ((y[:, None] + x[None, :]) / 2.0).clip(0.0, 1.0)
    flat = t.reshape(-1)

    channels = [
        np.interp(flat, GRADIENT_STOPS, GRADIENT_COLORS[:, index])
        for index in range(3)
    ]
    rgb = np.stack(channels, axis=-1).reshape(height, width, 3)
    return np.round(rgb).astype(np.uint8)


def apply_watermark(canvas: Image.Image, config: Config) -> Image.Image:
    watermark = load_image(str(asset_path("one-last-image-logo2.png")))
    watermark_width, watermark_height_total = watermark.size
    watermark_height = watermark_height_total // 2
    cut_top = watermark_height if config.hajimei else 0
    watermark_half = watermark.crop((0, cut_top, watermark_width, cut_top + watermark_height))

    width, height = canvas.size
    set_width = width * 0.3
    set_height = set_width / watermark_width * watermark_height

    if width / height > 1.1:
        set_height = height * 0.15
        set_width = set_height / watermark_height * watermark_width

    left = int(round(width - set_width - set_height * 0.2))
    top = int(round(height - set_height - set_height * 0.16))
    set_size = (max(1, int(round(set_width))), max(1, int(round(set_height))))

    overlay = watermark_half.resize(set_size, RESAMPLE_BILINEAR)
    result = canvas.copy()
    result.paste(overlay, (left, top), overlay)
    return result


def normalize_tone(tone: np.ndarray, config: Config) -> np.ndarray:
    denominator = 255.0 - config.light_cut - config.dark_cut
    if denominator <= 0:
        scale = 1.0
    else:
        scale = 255.0 / denominator
    tone = (tone - config.dark_cut) * scale
    return np.maximum(tone, 0.0)


def tone_to_rgba(tone: np.ndarray, config: Config, shade_map: Optional[np.ndarray]) -> Image.Image:
    tone = np.clip(tone, 0.0, 255.0)
    height, width = tone.shape

    if config.kuma:
        rgb = build_gradient_rgb(width, height)
        alpha = 255.0 - tone
        if shade_map is not None:
            alpha = np.maximum(alpha, shade_map)
        rgba = np.dstack([rgb, np.clip(alpha, 0.0, 255.0)]).astype(np.uint8)
        return Image.fromarray(rgba, mode="RGBA")

    gray = np.round(tone).astype(np.uint8)
    rgba = np.dstack([gray, gray, gray, np.full_like(gray, 255)]).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def smooth_canvas(image: Image.Image) -> Image.Image:
    width, height = image.size
    down_size = (max(1, int(width / 1.4)), max(1, int(height / 1.3)))
    return image.resize(down_size, RESAMPLE_BILINEAR).resize((width, height), RESAMPLE_BILINEAR)


def render_one_last_image(
    source: Image.Image,
    config: Config,
) -> Image.Image:
    working = resize_input(source, config)

    gray = rgba_to_gray(working)
    shade_map = None
    rng = np.random.default_rng(config.seed)

    if config.shade:
        shade_map = build_shade_map(gray.copy(), config, rng)

    if config.light:
        gray = gray + gray * (config.light / 100.0)

    if config.denoise:
        gray = convolve_gray(gray, average_kernel(3))

    kernel = CONVOLUTES.get(config.convolute_name)
    if kernel is not None:
        primary = convolve_gray(gray, kernel)
        if config.convolute1_diff:
            if config.convolute_name2:
                secondary_kernel = CONVOLUTES.get(config.convolute_name2)
                secondary = convolve_gray(gray, secondary_kernel) if secondary_kernel is not None else gray
            else:
                secondary = gray
            tone = 128.0 + secondary - primary
        else:
            tone = primary

        if config.light_cut or config.dark_cut:
            tone = normalize_tone(tone, config)
    else:
        tone = gray

    layer = tone_to_rgba(tone, config, shade_map)
    layer = smooth_canvas(layer)

    if config.watermark:
        layer = apply_watermark(layer, config)

    white = Image.new("RGB", layer.size, (255, 255, 255))
    white.paste(layer, mask=layer.getchannel("A"))
    return white


def make_side_by_side_diff(rendered: Image.Image, original: Image.Image) -> Image.Image:
    width, height = rendered.size
    result = Image.new("RGB", (width, height * 2), (255, 255, 255))
    result.paste(rendered.convert("RGB"), (0, 0))
    result.paste(original.convert("RGB").resize((width, height), RESAMPLE_BILINEAR), (0, height))
    return result


def make_diagonal_diff(rendered: Image.Image, original: Image.Image, bevel_position: int) -> Image.Image:
    width, height = rendered.size
    result = rendered.convert("RGB").copy()
    mask = Image.new("L", (width, height), 0)
    top_x = int(width * (bevel_position / 100.0 + 0.24))
    bottom_x = int(width * (bevel_position / 100.0 + 0.04))

    from PIL import ImageDraw

    draw = ImageDraw.Draw(mask)
    draw.polygon([(0, 0), (top_x, 0), (bottom_x, height), (0, height)], fill=255)

    original_layer = Image.new("RGB", (width, height), (0, 0, 0))
    original_layer.paste(original.convert("RGB"), (0, 0))
    result.paste(original_layer, (0, 0), mask)
    return result


def save_image(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()

    if suffix in {".jpg", ".jpeg"}:
        image.convert("RGB").save(output_path, quality=90, optimize=True)
        return

    if suffix == ".png":
        image.save(output_path)
        return

    image.convert("RGB").save(output_path.with_suffix(".jpg"), quality=90, optimize=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Python port of the One Last Image pipeline")
    parser.add_argument("input", type=Path, help="input image path")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output image path")
    parser.add_argument("--mode", choices=("normal", "diff", "diff2"), default="normal")
    parser.add_argument("--zoom", type=float, default=1.0)
    parser.add_argument("--cover", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--light", type=float, default=0.0)
    parser.add_argument("--shade-limit", type=int, default=108)
    parser.add_argument("--shade-light", type=int, default=80)
    parser.add_argument("--shade", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--kuma", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--hajimei", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--watermark", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--convolute-name", choices=tuple(CONVOLUTES.keys()), default="一般")
    parser.add_argument("--convolute-name2", choices=tuple(CONVOLUTES.keys()), default=None)
    parser.add_argument("--convolute1-diff", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--light-cut", type=int, default=128)
    parser.add_argument("--dark-cut", type=int, default=118)
    parser.add_argument("--denoise", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--bevel-position", type=int, default=20)
    parser.add_argument("--seed", type=int, default=None)
    return parser


def parse_args() -> tuple[Path, Path, Config, str]:
    parser = build_parser()
    args = parser.parse_args()
    config = Config(
        zoom=args.zoom,
        cover=args.cover,
        light=args.light,
        shade_limit=args.shade_limit,
        shade_light=args.shade_light,
        shade=args.shade,
        kuma=args.kuma,
        hajimei=args.hajimei,
        watermark=args.watermark,
        convolute_name=args.convolute_name,
        convolute1_diff=args.convolute1_diff,
        convolute_name2=args.convolute_name2,
        light_cut=args.light_cut,
        dark_cut=args.dark_cut,
        denoise=args.denoise,
        bevel_position=args.bevel_position,
        seed=args.seed,
    )
    return args.input, args.output, config, args.mode


def main() -> int:
    input_path, output_path, config, mode = parse_args()
    source = open_source_image(input_path)
    rendered = render_one_last_image(source, config)

    if mode == "diff":
        final_image = make_side_by_side_diff(rendered, source)
    elif mode == "diff2":
        final_image = make_diagonal_diff(rendered, source, config.bevel_position)
    else:
        final_image = rendered

    save_image(final_image, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())