"""Browser-rendered osu!mania map analysis commands.

The renderer is shared by ``/ma`` and the legacy ``/mapview``/``/rework``
handlers.  Keeping parsing here makes the command aliases behave identically
and leaves the existing file-analysis handlers available as a fallback.
"""

from __future__ import annotations

import asyncio
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Reply

from ..astrbot_service.errors import ManiaMapAnalyserError


MODE_FLAG_TO_CONTENT_BAR = {
    "-n": "None",
    "-a": "Auto",
    "-p": "Pattern",
    "-e": "Etterna",
    "-g": "Graph",
}
MOD_DEFAULT_SPEED = {"dt": 1.5, "ht": 0.75}

MA_REQUEST_RE = re.compile(
    r"^\s*/?(?P<command>ma|mag)(?P<graph>g|-g)?"
    r"(?P<tail>(?:\s+.*|[-+0-9].*|help(?:\s+.*)?)?)\s*$",
    re.IGNORECASE,
)

HELP_TEXT = "\n".join(
    [
        "osu!mania 谱面分析",
        "使用新的 ManiaMapAnalyser 前端渲染分析卡片。",
        "",
        "用法",
        "/ma <bid>      使用配置中的默认主体内容",
        "/ma -n <bid>   生成精简卡片",
        "/ma -a <bid>   根据 LN 占比自动选择 Pattern 或 Etterna",
        "/ma -p <bid>   显示 Pattern 键型分析",
        "/ma -e <bid>   显示 Etterna MSD 分析",
        "/ma -g <bid>   显示难度变化图，/mag 也可以",
        "/ma help       显示本帮助文本",
        "",
        "支持数字 bid、osu.ppy.sh 谱面链接，以及 +dt、+ht、+in、+ho 参数。",
        "示例：/ma 5170433+dt1.1",
    ]
)


def _normalize_bid(value: str) -> str | None:
    value = value.strip()
    if value.isdigit() and int(value) > 0:
        return value

    candidate = value if "://" in value else f"https://{value}"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname not in {"osu.ppy.sh", "osu.direct"}:
        return None

    fragment_match = re.fullmatch(r"(?:osu/|mania/)?(\d+)", parsed.fragment)
    if fragment_match and int(fragment_match.group(1)) > 0:
        return fragment_match.group(1)

    path_match = re.fullmatch(r"/(?:b|beatmaps?|osu)/(\d+)/?", parsed.path)
    if path_match and int(path_match.group(1)) > 0:
        return path_match.group(1)
    return None


def _build_runtime_overrides(mod_text: str) -> dict[str, str | float | None]:
    if not mod_text:
        return {}

    normalized = mod_text.strip().lower()
    mod = ""
    rate_text = ""
    for candidate in ("dt", "ht", "in", "ho"):
        if normalized.startswith(candidate):
            mod = candidate
            rate_text = normalized[len(candidate):]
            break

    if not mod:
        raise ManiaMapAnalyserError("目前仅支持 ht、dt、in、ho 四种 mod")

    if mod in {"in", "ho"}:
        if rate_text:
            raise ManiaMapAnalyserError(f"{mod.upper()} 不支持额外倍速参数")
        return {"cvtFlag": mod.upper()}

    speed_rate = MOD_DEFAULT_SPEED[mod]
    if rate_text:
        try:
            speed_rate = float(rate_text)
        except ValueError as exc:
            raise ManiaMapAnalyserError(f"{mod.upper()} 倍速参数无效：{rate_text}") from exc

    if not math.isfinite(speed_rate) or speed_rate <= 0:
        raise ManiaMapAnalyserError(f"{mod.upper()} 倍速必须大于 0")
    if mod == "ht" and not 0.5 <= speed_rate <= 0.99:
        raise ManiaMapAnalyserError("HT 倍速范围仅支持 0.5-0.99")
    if mod == "dt" and not 1.01 <= speed_rate <= 2:
        raise ManiaMapAnalyserError("DT 倍速范围仅支持 1.01-2")
    return {"speedRate": speed_rate}


def parse_request(raw_text: str) -> tuple[str | None, dict[str, str], dict[str, object]]:
    """Parse /ma, /mag and compact variants such as ``/mag5170433+dt``."""

    matched = MA_REQUEST_RE.match(raw_text or "")
    if not matched:
        raise ManiaMapAnalyserError("命令格式无效。输入 /ma help 查看用法。")

    normalized = re.sub(r"\s+", "", matched.group("tail") or "").lower()
    if not normalized or normalized in {"help", "-h", "--help"} or normalized.startswith("help"):
        return None, {}, {}

    content_bar = "Graph" if matched.group("graph") else None
    remaining = normalized
    if not matched.group("graph"):
        for mode_flag, mode_name in MODE_FLAG_TO_CONTENT_BAR.items():
            if remaining.startswith(mode_flag):
                content_bar = mode_name
                remaining = remaining[len(mode_flag):]
                break

    if not remaining:
        raise ManiaMapAnalyserError("缺少 bid。示例：/ma 5199917、/mag5170433+dt")

    bid_text, mod_text = remaining, ""
    if "+" in remaining:
        bid_text, mod_text = remaining.split("+", 1)
        if not bid_text or not mod_text or "+" in mod_text:
            raise ManiaMapAnalyserError(
                "命令格式不正确。示例：/ma 5199917、/mag5170433+dt、/ma-g5170433+ht0.75"
            )

    bid = _normalize_bid(bid_text)
    if bid is None:
        raise ManiaMapAnalyserError("bid 格式无效，请输入数字 ID 或 osu! 谱面链接")

    runtime = _build_runtime_overrides(mod_text)
    render = {"contentBar": content_bar} if content_bar else {}
    return bid, render, runtime


async def _render(
    plugin,
    event: AstrMessageEvent,
    status_message: str,
    generate,
    *generate_args,
):
    service = getattr(plugin, "render_service", None)
    if service is None:
        detail = str(getattr(plugin, "render_startup_error", "")).strip()
        suffix = f" 初始化失败：{detail}" if detail else "，请重载插件后重试。"
        yield event.plain_result("新的浏览器渲染器未初始化" + suffix)
        return

    if getattr(plugin, "render_semaphore", None) is not None:
        semaphore = plugin.render_semaphore
    else:
        semaphore = asyncio.Semaphore(1)

    if semaphore.locked():
        yield event.plain_result("当前谱面分析任务较多，请稍后再试。")
        return

    yield event.plain_result(status_message)
    try:
        async with semaphore:
            timeout = float(getattr(plugin, "render_timeout_seconds", 120.0))
            result = await asyncio.wait_for(
                asyncio.to_thread(generate, *generate_args),
                timeout=timeout,
            )
    except asyncio.TimeoutError:
        yield event.plain_result("谱面分析渲染超时，请稍后再试。")
        return
    except ManiaMapAnalyserError as exc:
        yield event.plain_result(str(exc))
        return
    except Exception as exc:
        logger.exception("map analysis render failed")
        yield event.plain_result(f"谱面分析渲染失败：{exc}")
        return

    image_path = result.get("image_path")
    if not image_path or not Path(image_path).is_file():
        yield event.plain_result("谱面分析没有生成有效图片，请检查日志。")
        return

    reply_id = getattr(getattr(event, "message_obj", None), "message_id", None)
    chain = []
    if reply_id:
        chain.append(Reply(id=reply_id))
    chain.append(Image.fromFileSystem(image_path))
    yield event.chain_result(chain)


async def render_bid(
    plugin,
    event: AstrMessageEvent,
    bid: str,
    render_overrides: dict[str, str],
    runtime_overrides: dict[str, object],
):
    service = getattr(plugin, "render_service", None)
    if service is None:
        detail = str(getattr(plugin, "render_startup_error", "")).strip()
        suffix = f" 初始化失败：{detail}" if detail else "，请重载插件后重试。"
        yield event.plain_result("新的浏览器渲染器未初始化" + suffix)
        return

    async for result in _render(
        plugin,
        event,
        "已收到谱面，正在生成分析卡片，请稍候...",
        service.generate_from_bid,
        bid,
        render_overrides,
        runtime_overrides,
    ):
        yield result


async def render_file(
    plugin,
    event: AstrMessageEvent,
    chart_path: Path,
    render_overrides: dict[str, str],
    runtime_overrides: dict[str, object],
):
    service = getattr(plugin, "render_service", None)
    if service is None:
        detail = str(getattr(plugin, "render_startup_error", "")).strip()
        suffix = f" 初始化失败：{detail}" if detail else "，请重载插件后重试。"
        yield event.plain_result("新的浏览器渲染器未初始化" + suffix)
        return

    async for result in _render(
        plugin,
        event,
        f"已收到文件：{chart_path.name}，正在生成分析卡片，请稍候...",
        service.generate_from_file,
        chart_path,
        render_overrides,
        runtime_overrides,
    ):
        yield result


async def run_mania_map(plugin, event: AstrMessageEvent):
    try:
        bid, render_overrides, runtime_overrides = parse_request(
            getattr(event, "message_str", "")
        )
    except ManiaMapAnalyserError as exc:
        yield event.plain_result(str(exc))
        return

    if bid is None:
        yield event.plain_result(HELP_TEXT)
        return

    async for result in render_bid(
        plugin, event, bid, render_overrides, runtime_overrides
    ):
        yield result


def parse_legacy_mapview_request(raw_text: str):
    """Use the toolkit parser for /mapview and return a new-renderer request."""

    from ..algorithm.utils import parse_cmd

    speed_rate, od_flag, cvt_flag, bid, _mod_display, errors = parse_cmd(raw_text)
    if bid is None and not errors:
        # The old parser intentionally required ``b<bid>``.  The new command
        # accepts plain IDs, so make that convenience available to the legacy
        # aliases without changing their existing x/OD/mod syntax.
        modern_text = re.sub(
            r"^\s*/?(?:mapview|rework)\b", "/ma", raw_text, flags=re.IGNORECASE
        )
        try:
            modern_bid, modern_render, modern_runtime = parse_request(modern_text)
        except ManiaMapAnalyserError:
            modern_bid = None
        if modern_bid is not None:
            return modern_bid, modern_render, modern_runtime
        parts = raw_text.split()
        for index, token in enumerate(parts):
            if token.startswith(("/", "-")):
                continue
            candidate = token.split("+", 1)[0]
            if _normalize_bid(candidate) is None:
                continue
            marker = f"b{candidate}"
            if "+" in token:
                marker += "+" + token.split("+", 1)[1]
            parts[index] = marker
            speed_rate, od_flag, cvt_flag, bid, _mod_display, errors = parse_cmd(
                " ".join(parts)
            )
            break
    if errors or bid is None:
        return None
    runtime: dict[str, object] = {"speedRate": speed_rate, "odFlag": od_flag}
    if cvt_flag:
        runtime["cvtFlag"] = cvt_flag[0]
    return str(bid), {}, runtime
