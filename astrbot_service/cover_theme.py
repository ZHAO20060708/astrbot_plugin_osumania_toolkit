"""从谱面封面提取主题色，供渲染桥的 osu! 三角纹主题使用。

整个模块都是「尽力而为」：任何一步失败都返回 None，渲染流程会退回到
默认的 osu! 粉色主题（且不垫 map 背景），绝不影响出图。
"""

from __future__ import annotations

import asyncio
import base64
import colorsys
import io
import logging
import re
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_USER_AGENT = "astrbot-osu-mania-map-analyser/1.0"

# osu! 封面资源按清晰度降级尝试：fullsize 才是「真·谱面背景」
_COVER_VARIANTS = ("fullsize.jpg", "cover@2x.jpg", "cover.jpg")
_COVER_HOST = "https://assets.ppy.sh/beatmaps/{set_id}/covers/{variant}"

# osz 下载源列表（按优先级排序）
_OSZ_DOWNLOAD_SOURCES = [
    "https://osu.direct/api/d/{set_id}",
    "https://catboy.best/d/{set_id}",
    "https://api.chimu.moe/v1/download/{set_id}?n=1",
]

# 垫在 pattern 块后面的封面：缩到这个宽度再编码，控制 payload 体积
_COVER_MAX_WIDTH = 800
_COVER_JPEG_QUALITY = 80

_BEATMAPSET_ID_RE = re.compile(r"(?mi)^\s*BeatmapSetID\s*:\s*(\d+)\s*$")


async def build_cover_theme(osu_text: str, cache_dir: Path) -> dict | None:
    """返回 {"accent": "#rrggbb", "coverDataUri": "data:image/jpeg;base64,...",
    "hasCover": True}；任何失败都返回 None。"""

    set_id = _parse_beatmapset_id(osu_text)
    if not set_id:
        logger.debug("未能从 osu 文件中解析出 BeatmapSetID，跳过封面主题")
        return None

    try:
        from PIL import Image
    except Exception as exc:
        logger.warning(f"Pillow 未安装或导入失败，无法加载封面主题: {exc}")
        return None

    raw = await _load_cover_bytes(set_id, cache_dir)
    if not raw:
        logger.info(f"未能下载 beatmapset {set_id} 的封面，使用默认主题")
        return None

    try:
        with Image.open(io.BytesIO(raw)) as im:
            rgb = im.convert("RGB")
            accent = _extract_accent(rgb, Image)
            cover_uri = _encode_cover_data_uri(rgb, Image)
    except Exception as exc:
        logger.warning(f"处理封面图片失败 (set_id={set_id}): {exc}")
        return None

    if not accent or not cover_uri:
        logger.warning(f"提取主题色或编码封面失败 (set_id={set_id})")
        return None

    logger.info(f"成功为 beatmapset {set_id} 构建封面主题 (accent={accent})")
    return {
        "accent": accent,
        "coverDataUri": cover_uri,
        "hasCover": True,
    }


def _parse_beatmapset_id(osu_text: str) -> str | None:
    match = _BEATMAPSET_ID_RE.search(osu_text or "")
    if not match:
        return None
    set_id = match.group(1)
    return set_id if set_id and set_id != "-1" else None


async def _load_cover_bytes(set_id: str, cache_dir: Path) -> bytes | None:
    """从缓存或网络异步加载封面图片的字节数据"""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.debug(f"创建封面缓存目录失败: {exc}")
        cache_dir = None

    # 1. 尝试从缓存读取封面
    cached = cache_dir / f"{set_id}.cover" if cache_dir else None
    if cached and cached.is_file() and cached.stat().st_size > 0:
        try:
            logger.debug(f"从缓存加载封面: {cached}")
            return await asyncio.to_thread(cached.read_bytes)
        except Exception as exc:
            logger.debug(f"读取缓存封面失败: {exc}")

    # 2. 先尝试从 CDN 直接下载封面图片（快速路径）
    for variant in _COVER_VARIANTS:
        url = _COVER_HOST.format(set_id=set_id, variant=variant)
        logger.debug(f"尝试下载封面: {url}")
        data = await _http_get_async(url)
        if data:
            logger.info(f"成功下载封面 {variant} (set_id={set_id}, size={len(data)} bytes)")
            if cached:
                try:
                    await asyncio.to_thread(cached.write_bytes, data)
                    logger.debug(f"封面已缓存到: {cached}")
                except Exception as exc:
                    logger.debug(f"写入封面缓存失败: {exc}")
            return data
        else:
            logger.debug(f"下载 {variant} 失败，尝试下一个变体")

    # 3. CDN 失败后，尝试下载 osz 文件并提取背景
    logger.info(f"CDN 封面下载失败，尝试从 osz 提取 (set_id={set_id})")
    cover_data = await _extract_cover_from_osz_async(set_id, cache_dir)
    if cover_data:
        logger.info(f"成功从 osz 提取封面 (set_id={set_id}, size={len(cover_data)} bytes)")
        # 写入缓存
        if cached:
            try:
                await asyncio.to_thread(cached.write_bytes, cover_data)
                logger.debug(f"封面已缓存到: {cached}")
            except Exception as exc:
                logger.debug(f"写入封面缓存失败: {exc}")
        return cover_data

    logger.warning(f"无法获取封面 (set_id={set_id})")
    return None


async def _extract_cover_from_osz_async(set_id: str, cache_dir: Path | None) -> bytes | None:
    """异步下载 osz 文件并从中提取背景图片"""
    # 下载 osz 到临时位置
    osz_cache_path = cache_dir / f"{set_id}.osz" if cache_dir else None

    # 如果已有缓存的 osz，直接使用
    if osz_cache_path and osz_cache_path.is_file():
        logger.debug(f"使用缓存的 osz: {osz_cache_path}")
        osz_data = None
        osz_path = osz_cache_path
    else:
        # 尝试从多个镜像源下载 osz
        osz_data = None
        for source_url in _OSZ_DOWNLOAD_SOURCES:
            url = source_url.format(set_id=set_id)
            logger.debug(f"尝试从镜像下载 osz: {url}")
            osz_data = await _http_get_async(url, timeout=45)
            if osz_data:
                logger.info(f"成功从镜像下载 osz (set_id={set_id}, size={len(osz_data)} bytes)")
                break
            else:
                logger.debug(f"从 {source_url.split('/')[2]} 下载失败，尝试下一个镜像")

        if not osz_data:
            logger.debug(f"所有镜像源下载 osz 均失败 (set_id={set_id})")
            return None

        # 缓存 osz 文件（可选）
        if osz_cache_path:
            try:
                await asyncio.to_thread(osz_cache_path.write_bytes, osz_data)
                logger.debug(f"osz 已缓存到: {osz_cache_path}")
            except Exception as exc:
                logger.debug(f"写入 osz 缓存失败: {exc}")

        osz_path = None

    # 从 osz (zip) 中提取背景图片
    try:
        if osz_path:
            # 从文件路径打开
            cover_data = await asyncio.to_thread(_extract_from_zip_file, osz_path, set_id)
        else:
            # 从字节数据打开
            cover_data = await asyncio.to_thread(_extract_from_zip_bytes, osz_data, set_id)

        return cover_data
    except Exception as exc:
        logger.debug(f"从 osz 提取背景失败 (set_id={set_id}): {exc}")
        return None


def _extract_from_zip_file(osz_path: Path, set_id: str) -> bytes | None:
    """从 zip 文件路径提取背景（同步操作，用于 asyncio.to_thread）"""
    with zipfile.ZipFile(osz_path, 'r') as zf:
        return _find_background_in_zip(zf, set_id)


def _extract_from_zip_bytes(osz_data: bytes, set_id: str) -> bytes | None:
    """从 zip 字节数据提取背景（同步操作，用于 asyncio.to_thread）"""
    with zipfile.ZipFile(io.BytesIO(osz_data), 'r') as zf:
        return _find_background_in_zip(zf, set_id)


def _find_background_in_zip(zf: zipfile.ZipFile, set_id: str) -> bytes | None:
    """在 zip 文件中查找背景图片

    策略：
    1. 解析第一个 .osu 文件，找到 [Events] 中的背景文件名
    2. 如果没找到，尝试常见的背景文件名模式
    """
    file_list = zf.namelist()

    # 找到第一个 .osu 文件
    osu_files = [f for f in file_list if f.lower().endswith('.osu')]
    if not osu_files:
        logger.debug(f"osz 中没有找到 .osu 文件 (set_id={set_id})")
        return None

    # 解析 .osu 文件找背景
    bg_filename = None
    try:
        with zf.open(osu_files[0]) as f:
            content = f.read().decode('utf-8-sig', errors='replace')
            bg_filename = _parse_background_filename(content)
    except Exception as exc:
        logger.debug(f"解析 .osu 文件失败: {exc}")

    # 如果解析到了背景文件名
    if bg_filename:
        # 在 zip 中查找匹配的文件（不区分大小写）
        bg_lower = bg_filename.lower()
        for zip_file in file_list:
            if zip_file.lower() == bg_lower or zip_file.lower().endswith('/' + bg_lower):
                try:
                    logger.debug(f"找到背景文件: {zip_file}")
                    return zf.read(zip_file)
                except Exception as exc:
                    logger.debug(f"读取背景文件失败 ({zip_file}): {exc}")

    # 如果没找到，尝试常见图片文件（jpg/jpeg/png）作为 fallback
    image_files = [f for f in file_list
                   if f.lower().endswith(('.jpg', '.jpeg', '.png'))
                   and not f.startswith('__MACOSX')]

    if image_files:
        # 优先选择文件名包含 bg/background 的
        for pattern in ['bg', 'background', 'cover']:
            for img in image_files:
                if pattern in img.lower():
                    try:
                        logger.debug(f"fallback: 使用图片文件 {img}")
                        return zf.read(img)
                    except Exception as exc:
                        logger.debug(f"读取图片文件失败 ({img}): {exc}")

        # 否则使用第一个图片
        try:
            logger.debug(f"fallback: 使用第一个图片文件 {image_files[0]}")
            return zf.read(image_files[0])
        except Exception as exc:
            logger.debug(f"读取图片文件失败 ({image_files[0]}): {exc}")

    logger.debug(f"osz 中没有找到可用的背景图片 (set_id={set_id})")
    return None


def _parse_background_filename(osu_text: str) -> str | None:
    """从 .osu 文件内容中解析背景文件名

    格式: 0,0,"bg.jpg",0,0
    """
    # 匹配 [Events] 区块中的背景事件
    # 格式: 0,0,"filename.jpg" 或 0,0,"filename.jpg",0,0
    match = re.search(
        r'(?m)^\s*0\s*,\s*0\s*,\s*"([^"]+)"',
        osu_text
    )
    if match:
        filename = match.group(1).strip()
        logger.debug(f"从 .osu 解析到背景文件: {filename}")
        return filename
    return None


async def _http_get_async(url: str, timeout: int = 30) -> bytes | None:
    """异步 HTTP GET 请求"""
    try:
        import aiohttp
    except ImportError:
        logger.warning("aiohttp 未安装，无法进行异步 HTTP 请求")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status != 200:
                    logger.debug(f"HTTP 请求失败，状态码: {response.status}")
                    return None
                data = await response.read()
                return data or None
    except asyncio.TimeoutError:
        logger.debug(f"HTTP 请求超时 ({url})")
        return None
    except Exception as exc:
        logger.debug(f"HTTP 请求失败 ({url}): {exc}")
        return None


def _extract_accent(rgb_image, image_module) -> str | None:
    """挑一个鲜艳、又有代表性的主色。"""
    try:
        small = rgb_image.copy()
        small.thumbnail((110, 110))
        quantized = small.quantize(colors=12, method=image_module.Quantize.MEDIANCUT)
        palette = quantized.getpalette() or []
        color_counts = quantized.getcolors() or []
    except Exception:
        return None

    best_score = -1.0
    best_rgb: tuple[int, int, int] | None = None
    total = sum(count for count, _ in color_counts) or 1

    for count, index in color_counts:
        base = index * 3
        if base + 2 >= len(palette):
            continue
        r, g, b = palette[base], palette[base + 1], palette[base + 2]
        h, lightness, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        freq = count / total
        # 偏好：够鲜艳 + 亮度适中（不要纯黑纯白）+ 占比别太小
        brightness_fit = 1.0 - abs(lightness - 0.55) * 1.4
        brightness_fit = max(brightness_fit, 0.05)
        score = (freq ** 0.5) * (0.25 + s * 1.35) * brightness_fit
        if score > best_score:
            best_score = score
            best_rgb = (r, g, b)

    if best_rgb is None:
        return None

    return _normalize_accent(*best_rgb)


def _normalize_accent(r: int, g: int, b: int) -> str:
    """把主色压进一个「好看且可读」的区间，避免太暗/太灰/太刺眼。"""
    h, lightness, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)

    if s < 0.15:
        # 近乎灰度的封面：给一点点饱和，让主题呈现「带色调的石板蓝/灰」而非死灰，
        # 但仍贴着封面里本就存在的色相，不凭空造色
        s = max(s, 0.18)
        lightness = min(max(lightness, 0.43), 0.56)
    else:
        s = min(max(s, 0.5), 0.9)
        lightness = min(max(lightness, 0.46), 0.62)

    nr, ng, nb = colorsys.hls_to_rgb(h, lightness, s)
    return "#{:02x}{:02x}{:02x}".format(
        round(nr * 255), round(ng * 255), round(nb * 255)
    )


def _encode_cover_data_uri(rgb_image, image_module) -> str | None:
    try:
        cover = rgb_image
        if cover.width > _COVER_MAX_WIDTH:
            ratio = _COVER_MAX_WIDTH / cover.width
            new_size = (_COVER_MAX_WIDTH, max(1, round(cover.height * ratio)))
            cover = cover.resize(new_size, image_module.Resampling.LANCZOS)

        buffer = io.BytesIO()
        cover.save(buffer, format="JPEG", quality=_COVER_JPEG_QUALITY, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return None

    return f"data:image/jpeg;base64,{encoded}"
