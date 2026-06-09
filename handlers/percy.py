"""LN skin "投机取巧程度" inspect/modify: /percy (alias /投皮).

Takes a replied .png LN body skin image. With no target value it reports the current
degree; with a value it rewrites the skin to that degree (optionally in Lazer mode).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image

from ..file.cache import CACHE_DIR
from ..file.path import safe_filename
from ..file.cleanup import cleanup_temp_file
from ..algorithm.percy import get_current_d, process_ln_image, parse_percy_cmd, LNImageError


async def run_percy(plugin, event: AstrMessageEvent):
    cmd_text = event.message_str.strip()
    d, lzr_flag, err_msg = parse_percy_cmd(cmd_text)
    if err_msg:
        yield event.plain_result(f"命令参数错误：{', '.join(err_msg)}")
        return

    from ..helpers import get_attached_file

    try:
        found = await get_attached_file(event, (".png",), include_image=True)
    except ValueError as e:
        yield event.plain_result(str(e))
        return
    if not found:
        yield event.plain_result("请回复一条包含图片文件的消息。")
        return

    src_path, file_name = found
    mode_text = "Lazer)约" if lzr_flag else "Stable)"
    output_path = CACHE_DIR / f"processed_{safe_filename(file_name)}"

    try:
        if d is None:
            current_d = await asyncio.to_thread(get_current_d, src_path)
            if current_d is not None:
                current_d = (current_d + 75) if lzr_flag else current_d
                yield event.plain_result(f"当前图片投机取巧程度({mode_text}为{current_d}px。")
            else:
                yield event.plain_result("无法识别当前图片的投机取巧程度。")
            return

        await process_ln_image(src_path, d, lzr_flag, output_path)
        yield event.chain_result([Image.fromFileSystem(str(output_path))])
    except LNImageError as e:
        yield event.plain_result(f"图片结构不正确：{str(e)}")
    except Exception as e:
        logger.exception("percy 处理失败")
        yield event.plain_result(f"处理过程中发生错误: {str(e)}")
    finally:
        if output_path and Path(output_path).exists():
            asyncio.create_task(cleanup_temp_file(Path(output_path)))
