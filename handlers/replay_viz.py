"""Replay-visualisation commands: /lifebar, /spectrum, /pressingtime.

Each takes a replied .osr (and .mr for spectrum/pressingtime) replay, parses it,
and renders a matplotlib chart that is sent back as an image.
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
from ..parser.mr_file_parser import mr_file
from ..algorithm.conversion import convert_mr_to_osr
from ..helpers import get_attached_file

_STATUS_ERRORS = {
    "NotMania": "该回放不是 Mania 模式。",
    "tooFewKeys": "有效轨道数量过少，无法分析。",
    "init": "回放尚未process。",
}


async def _run_replay_viz(event: AstrMessageEvent, plot_func, *, allow_mr: bool):
    exts = (".osr", ".mr") if allow_mr else (".osr",)
    try:
        found = await get_attached_file(event, exts)
    except ValueError as e:
        yield event.plain_result(str(e))
        return
    if not found:
        yield event.plain_result("请回复一条包含回放文件的消息。")
        return

    file_path, file_name = found
    yield event.plain_result(f"已收到文件：{file_name}，请稍候...")

    output_path = None
    try:
        if file_name.lower().endswith(".mr"):
            mr_obj = await asyncio.to_thread(mr_file, file_path)
            data = await asyncio.to_thread(convert_mr_to_osr, mr_obj)
        else:
            data = await asyncio.to_thread(osr_file, file_path)
            await asyncio.to_thread(data.process)

        if data.status in _STATUS_ERRORS:
            yield event.plain_result(_STATUS_ERRORS[data.status])
            return

        output_path = await asyncio.to_thread(plot_func, data, str(CACHE_DIR))
        yield event.chain_result([Image.fromFileSystem(output_path)])
    except Exception as e:
        logger.exception("处理回放时出错")
        yield event.plain_result(f"处理过程中发生错误：{type(e).__name__}: {e}")
    finally:
        if output_path and Path(output_path).exists():
            asyncio.create_task(cleanup_temp_file(Path(output_path)))


async def run_lifebar(plugin, event: AstrMessageEvent):
    from ..render.lifebar import plot_life

    async for r in _run_replay_viz(event, plot_life, allow_mr=False):
        yield r


async def run_spectrum(plugin, event: AstrMessageEvent):
    from ..render.spectrum import plot_spectrum

    async for r in _run_replay_viz(event, plot_spectrum, allow_mr=True):
        yield r


async def run_pressingtime(plugin, event: AstrMessageEvent):
    from ..render.pressingtime import plot_pressingtime

    async for r in _run_replay_viz(event, plot_pressingtime, allow_mr=True):
        yield r
