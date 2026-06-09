"""Judgement-visualisation commands: /delta, /scatter.

Both require a replied .osr/.mr replay AND a beatmap id (b<bid> / mania url): the
replay is matched against the chart and a per-column matplotlib plot is returned.
(In the upstream plugin the no-bid branch is unreachable, so these are non-interactive.)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image

from ..file.cache import CACHE_DIR
from ..file.cleanup import cleanup_temp_file
from ..parser.osr_file_parser import osr_file
from ..parser.osu_file_parser import osu_file
from ..parser.mr_file_parser import mr_file
from ..api.osu import download_file_by_id
from ..algorithm.utils import parse_cmd
from ..algorithm.conversion import convert_mr_to_osr
from ..helpers import get_attached_file

_REPLAY_STATUS_ERRORS = {
    "NotMania": "该回放不是 Mania 模式。",
    "tooFewKeys": "有效轨道数量过少，无法分析。",
    "init": "回放尚未process。",
}


async def _run_delta_scatter(event: AstrMessageEvent, plot_func):
    cmd_text = event.message_str.strip()
    *_, bid, _mod_display, cmd_err = parse_cmd(cmd_text)
    if cmd_err:
        yield event.plain_result("错误:\n" + "\n".join(cmd_err) + "\n请检查命令格式并重试。")
        return
    if not bid:
        yield event.plain_result("请回复一条包含回放文件的消息，同时使用 b<谱面ID> 指定谱面。")
        return

    try:
        found = await get_attached_file(event, (".osr", ".mr"))
    except ValueError as e:
        yield event.plain_result(str(e))
        return
    if not found:
        yield event.plain_result("请回复一条包含回放文件的消息。")
        return
    osr_path, file_name = found

    osu_path = None
    output_path = None
    try:
        if file_name.lower().endswith(".mr"):
            mr_obj = await asyncio.to_thread(mr_file, osr_path)
            osr = await asyncio.to_thread(convert_mr_to_osr, mr_obj)
        else:
            osr = await asyncio.to_thread(osr_file, osr_path)
            await asyncio.to_thread(osr.process)

        if osr.status in _REPLAY_STATUS_ERRORS:
            yield event.plain_result(_REPLAY_STATUS_ERRORS[osr.status])
            return

        osu_path, _osu_name = await download_file_by_id(CACHE_DIR, bid)
        osu = await asyncio.to_thread(osu_file, osu_path)
        await asyncio.to_thread(osu.process)
        if osu.status == "NotMania":
            yield event.plain_result("该谱面不是 Mania 模式。")
            return
        if osu.status == "init":
            yield event.plain_result("谱面尚未process。")
            return

        yield event.plain_result("已收到文件，请稍候...")
        output_path = await asyncio.to_thread(plot_func, osr, osu, str(CACHE_DIR))
        yield event.chain_result([Image.fromFileSystem(output_path)])
    except Exception as e:
        logger.exception("处理回放时出错")
        yield event.plain_result(f"处理过程中发生错误：{type(e).__name__}: {e}")
    finally:
        if osu_path and Path(osu_path).exists():
            asyncio.create_task(cleanup_temp_file(Path(osu_path)))
        if output_path and Path(output_path).exists():
            asyncio.create_task(cleanup_temp_file(Path(output_path)))


async def run_delta(plugin, event: AstrMessageEvent):
    from ..render.delta import plot_delta

    async for r in _run_delta_scatter(event, plot_delta):
        yield r


async def run_scatter(plugin, event: AstrMessageEvent):
    from ..render.scatter import plot_scatter

    async for r in _run_delta_scatter(event, plot_scatter):
        yield r
