"""Map key-pattern analysis + difficulty estimation: /mapview (alias /rework).

Accepts a replied .osu/.mc chart, an .osz/.mcz mapset (batch -> forwarded cards),
or a beatmap id / mania url. Renders a glass-style HTML difficulty card per chart.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image, Plain

from ..file.cache import CACHE_DIR
from ..file.cleanup import cleanup_temp_file
from ..algorithm.utils import parse_cmd
from ..algorithm.mapview import (
    analyze_mapview_chart,
    analyze_mapview_zip,
    format_mapview_result_text,
    format_parse_error_for_user,
)
from ..algorithm.pattern import PatternNotManiaError, PatternParseError
from ..algorithm.estimator.exceptions import ParseError, NotManiaError
from ..render.mapview import render_analysis_card
from ..helpers import get_attached_file, forward_results
from .mania_map import parse_legacy_mapview_request, render_bid, render_file

_CHART_EXTS = (".osu", ".mc", ".osz", ".mcz")


async def run_mapview(plugin, event: AstrMessageEvent):
    cmd_text = event.message_str.strip()
    speed_rate, od_flag, cvt_flag, bid, mod_display, err_msg = parse_cmd(cmd_text)
    if err_msg:
        yield event.plain_result("错误:\n" + "\n".join(err_msg) + "\n请检查命令格式并重试。")
        return

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
                rows, errors, total = await analyze_mapview_zip(
                    chart_path, speed_rate, od_flag, cvt_flag, mod_display, CACHE_DIR
                )
                if not rows and not errors:
                    yield event.plain_result("图包中没有可分析的谱面文件。")
                    return
                if not rows:
                    yield event.plain_result("错误:\n" + "\n".join(errors))
                    return
                if total >= 3:
                    yield event.plain_result(f"分析完成，有效 {len(rows)} / {total}，正在生成图片...")
                items = await _build_card_items(rows)
                if errors:
                    items.append("部分谱面分析失败:\n" + "\n".join(errors))
                async for r in forward_results(event, items):
                    yield r
                return
            else:
                # The modern renderer can accept .osu directly. Convert Malody
                # charts first so attachment users get the same card as BID users.
                if getattr(plugin, "render_service", None) is not None:
                    render_path = chart_path
                    converted_path = None
                    try:
                        if file_name.lower().endswith(".mc"):
                            from ..algorithm.conversion import convert_mc_to_osu

                            converted_path = Path(
                                await asyncio.to_thread(
                                    convert_mc_to_osu,
                                    str(chart_path),
                                    str(CACHE_DIR),
                                )
                            )
                            render_path = converted_path
                        runtime: dict[str, object] = {
                            "speedRate": speed_rate,
                            "odFlag": od_flag,
                        }
                        if cvt_flag:
                            runtime["cvtFlag"] = cvt_flag[0]
                        async for r in render_file(
                            plugin, event, render_path, {}, runtime
                        ):
                            yield r
                    finally:
                        if converted_path and converted_path.exists():
                            asyncio.create_task(cleanup_temp_file(converted_path))
                    return
                yield event.plain_result(f"已收到文件：{file_name}，正在生成图片...")
                row = await analyze_mapview_chart(
                    chart_path, file_name, speed_rate, od_flag, cvt_flag, mod_display, CACHE_DIR
                )
                async for r in _send_single_card(event, row):
                    yield r
                return

        if bid is not None:
            modern_request = parse_legacy_mapview_request(cmd_text)
            if modern_request is not None and getattr(plugin, "render_service", None):
                modern_bid, render_overrides, runtime = modern_request
                async for r in render_bid(
                    plugin, event, modern_bid, render_overrides, runtime
                ):
                    yield r
                return
            chart_path, file_name = await _download_by_id(bid)
            row = await analyze_mapview_chart(
                chart_path, file_name, speed_rate, od_flag, cvt_flag, mod_display, CACHE_DIR
            )
            async for r in _send_single_card(event, row):
                yield r
            return

        yield event.plain_result(
            "请回复包含 .osu/.mc/.osz/.mcz 文件的消息，或使用 bid/mania 谱面网址指定谱面。"
        )
    except (ParseError, PatternParseError) as e:
        yield event.plain_result(format_parse_error_for_user(e))
    except (NotManiaError, PatternNotManiaError):
        yield event.plain_result("该谱面不是 mania 模式，无法分析。")
    except Exception as e:
        text = str(e)
        if "超过" in text or "过大" in text:
            yield event.plain_result(
                "分析失败：文件过大。\n建议：可以删除图包内的媒体文件（音频/背景视频/图片）后再重新打包上传。"
            )
        elif "max() iterable argument is empty" in text:
            yield event.plain_result(f"错误: 未找到谱面 b{bid}，请检查bid是否正确")
        else:
            yield event.plain_result(f"分析失败：{e}")
    finally:
        if chart_path and Path(chart_path).exists():
            asyncio.create_task(cleanup_temp_file(Path(chart_path)))


async def _download_by_id(bid: int):
    from ..api.osu import download_file_by_id

    return await download_file_by_id(CACHE_DIR, bid)


async def _build_card_items(rows: list) -> list:
    items: list = []
    for row in rows:
        try:
            img_path = await render_analysis_card(row["template"])
            items.append([Plain(f"{row['file_name']}\n"), Image.fromFileSystem(img_path)])
        except Exception:
            logger.exception("mapview card render failed")
            items.append(f"{row['file_name']}:\n{format_mapview_result_text(row)}")
    return items


async def _send_single_card(event: AstrMessageEvent, row: dict):
    try:
        img_path = await render_analysis_card(row["template"])
        yield event.chain_result([Image.fromFileSystem(img_path)])
    except Exception:
        logger.exception("mapview card render failed")
        yield event.plain_result(format_mapview_result_text(row))
