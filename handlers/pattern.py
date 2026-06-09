"""Chart key-pattern analysis: /pattern (alias /键型).

Accepts a replied .osu/.mc chart, an .osz/.mcz mapset, or a beatmap id / mania url.
Returns an HTML pattern card (single chart) or a forwarded set of cards (mapset).
Adding -d / -detail forces forwarded plain-text reports instead of cards.

NOTE: the upstream matcher's file-reply branch is broken (the single-chart path is
nested inside the .osz `if` with no `else`, so plain .osu/.mc replies analyse nothing
and .osz replies get overwritten by a single-chart pass over the zip itself). This
port implements the clearly-intended behaviour, matching the correct /mapview & /ett
structure: .osz/.mcz -> batch, .osu/.mc -> single card.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from ..file.cache import CACHE_DIR
from ..config import Config, get_plugin_config
from ..algorithm.conversion import convert_mc_to_osu
from ..algorithm.utils import (
    parse_cmd,
    is_mc_file,
    resolve_meta_data,
    extract_zip_file,
)
from ..algorithm.pattern import (
    PatternNotManiaError,
    PatternParseError,
    analyze_pattern_file,
    format_pattern_result_text,
)
from ..algorithm.pattern.card import build_pattern_card_data
from ..render.pattern import render_pattern_card
from ..helpers import get_attached_file, forward_results

_config = get_plugin_config(Config)
_CHART_EXTS = (".osu", ".mc", ".osz", ".mcz")


@dataclass
class _Row:
    file_name: str
    text: str
    card_data: dict[str, Any] | None


def _is_detail_mode(cmd_text: str) -> bool:
    tokens = {part.strip().lower() for part in cmd_text.split()}
    return bool(tokens & {"-d", "-detail", "--detail"})


async def _analyze_single_chart(chart_file: Path, file_name: str, rate: float) -> _Row:
    target_file = chart_file
    target_name = file_name
    if is_mc_file(str(target_file)):
        osu_file_path = await asyncio.to_thread(convert_mc_to_osu, str(target_file), str(CACHE_DIR))
        target_file = Path(osu_file_path)
        target_name = os.path.basename(osu_file_path)

    report = await analyze_pattern_file(str(target_file), rate=rate)
    meta_data = resolve_meta_data(target_file, target_name)
    return _Row(
        file_name=target_name,
        text=format_pattern_result_text(meta_data, report, rate=rate),
        card_data=build_pattern_card_data(meta_data, report, rate=rate),
    )


async def _analyze_zip(zip_file: Path, rate: float) -> tuple[list[_Row], int]:
    temp_dir = CACHE_DIR / f"pattern_batch_{int(time.time())}_{os.getpid()}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        try:
            chart_files = await asyncio.to_thread(extract_zip_file, zip_file, temp_dir)
        except Exception as e:
            return [_Row(zip_file.name, f"图包分析失败 - {e}", None)], 0
        if not chart_files:
            return [_Row(zip_file.name, "图包中没有可分析的谱面文件。", None)], 0

        total = len(chart_files)
        max_charts = _config.batch_max_charts
        if max_charts > 0 and total > max_charts:
            chart_files = chart_files[:max_charts]

        results: list[_Row] = []
        errors: list[str] = []
        for chart_file in chart_files:
            try:
                results.append(await _analyze_single_chart(chart_file, chart_file.name, rate))
                await asyncio.sleep(0)
            except PatternNotManiaError:
                errors.append(f"{chart_file.name}: 不是 mania 模式")
            except PatternParseError as e:
                errors.append(f"{chart_file.name}: 谱面解析失败 - {e}")
            except Exception as e:
                errors.append(f"{chart_file.name}: 分析失败 - {e}")
        if errors:
            results.append(_Row("errors", "部分谱面分析失败:\n" + "\n".join(errors), None))
        return results, total
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


async def _emit(event: AstrMessageEvent, rows: list[_Row], detail_mode: bool):
    if detail_mode or not rows:
        texts = [r.text for r in rows] if rows else ["图包中没有可分析的谱面文件。"]
        async for r in forward_results(event, texts):
            yield r
        return

    if any(r.card_data is None for r in rows):
        async for r in forward_results(event, [r.text for r in rows]):
            yield r
        return

    if len(rows) == 1:
        try:
            path = await render_pattern_card(rows[0].card_data or {})
            yield event.chain_result([Image.fromFileSystem(path)])
        except Exception:
            logger.exception("pattern card render failed")
            yield event.plain_result(rows[0].text)
        return

    items: list = []
    for row in rows:
        try:
            path = await render_pattern_card(row.card_data or {})
            items.append([Plain(f"{row.file_name}\n"), Image.fromFileSystem(path)])
        except Exception:
            logger.exception("pattern card render failed")
            items.append(f"{row.file_name}:\n{row.text}")
    async for r in forward_results(event, items):
        yield r


async def run_pattern(plugin, event: AstrMessageEvent):
    cmd_text = event.message_str.strip()
    detail_mode = _is_detail_mode(cmd_text)
    *_, bid, _md, _err = parse_cmd(cmd_text)

    chart_path = None
    try:
        try:
            found = await get_attached_file(event, _CHART_EXTS)
        except ValueError as e:
            yield event.plain_result(str(e))
            return

        if found is not None:
            chart_path, file_name = found
            if file_name.lower().endswith((".osz", ".mcz")):
                yield event.plain_result(f"已收到图包：{file_name}，正在分析，请稍候...")
                rows, total = await _analyze_zip(chart_path, rate=1.0)
                if total >= 3:
                    available = sum(1 for r in rows if r.card_data is not None)
                    yield event.plain_result(f"分析完成，有效 {available} / {total}")
                async for r in _emit(event, rows, detail_mode):
                    yield r
                return
            yield event.plain_result(f"已收到文件：{file_name}，请稍候...")
            rows = [await _analyze_single_chart(chart_path, file_name, rate=1.0)]
            async for r in _emit(event, rows, detail_mode):
                yield r
            return

        if bid is not None:
            from ..api.osu import download_file_by_id

            chart_path, file_name = await download_file_by_id(CACHE_DIR, bid)
            rows = [await _analyze_single_chart(chart_path, file_name, rate=1.0)]
            async for r in _emit(event, rows, detail_mode):
                yield r
            return

        yield event.plain_result(
            "请回复包含 .osu/.mc/.osz/.mcz 文件的消息，或使用 bid/mania 谱面网址指定谱面。"
        )
    except PatternNotManiaError:
        yield event.plain_result("该谱面不是 mania 模式，无法分析键型。")
    except PatternParseError as e:
        yield event.plain_result(f"谱面解析失败：{e}")
    except Exception as e:
        text = str(e)
        if "超过" in text or "过大" in text:
            yield event.plain_result(
                "键型分析失败：文件过大。\n建议：可以删除图包内的媒体文件（音频/背景视频/图片）后再重新打包上传。"
            )
        else:
            yield event.plain_result(f"键型分析失败：{e}")
    finally:
        if chart_path and Path(chart_path).exists():
            asyncio.create_task(_safe_unlink(Path(chart_path)))


async def _safe_unlink(path: Path):
    try:
        path.unlink()
    except OSError:
        pass
