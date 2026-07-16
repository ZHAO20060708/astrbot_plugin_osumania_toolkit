"""Help command: /omtk.

/omtk            -> main menu
/omtk <cmd>      -> all help pages for a command (merged-forward)
/omtk <cmd> <n>  -> a specific help page
"""

from __future__ import annotations

import re

from astrbot.api.event import AstrMessageEvent

from ..config import Config, get_plugin_config
from ..data import omtk_help_data
from ..helpers import forward_results

_config = get_plugin_config(Config)
_LIMIT_TEXT_RE = re.compile(r"单文件大小 (?:\d+|无限制) MB; 处理上限 (?:\d+|无限制) 个")


def _strip_command(message_str: str) -> list[str]:
    parts = message_str.strip().split()
    if parts and parts[0].lstrip("/").lower() == "omtk":
        parts = parts[1:]
    return parts


def _render_runtime_values(text: str) -> str:
    max_size = _config.max_file_size_mb if _config.max_file_size_mb > 0 else "无限制"
    max_charts = _config.batch_max_charts if _config.batch_max_charts > 0 else "无限制"
    return _LIMIT_TEXT_RE.sub(
        f"单文件大小 {max_size} MB; 处理上限 {max_charts} 个", text
    )


async def run_omtk(plugin, event: AstrMessageEvent):
    parts = _strip_command(event.message_str)

    if len(parts) == 0:
        yield event.plain_result(omtk_help_data.main_menu_text)
        return
    if len(parts) > 2:
        yield event.plain_result("请检查命令格式后重试。")
        return

    cmd_name = parts[0].lower()
    cmd_name = omtk_help_data.command_aliases.get(cmd_name, cmd_name)

    matched: list[tuple[str, str]] = []
    for cmd_type, type_name, page, total_pages, text in omtk_help_data.help_text:
        if cmd_name != cmd_type:
            continue
        text = _render_runtime_values(text)
        if total_pages == "1":
            content = f"{cmd_type}({type_name}):\n{text}"
        else:
            content = f"{cmd_type}({type_name}):\n{text}\n (第 {page} 页，共 {total_pages} 页)"
        matched.append((page, content))

    if not matched:
        yield event.plain_result("无效的命令类型或页码。")
        return

    if len(parts) == 2:
        for page, content in matched:
            if parts[1] == page:
                yield event.plain_result(content)
                return
        yield event.plain_result("无效的命令类型或页码。")
        return

    matched.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
    async for r in forward_results(event, [content for _, content in matched]):
        yield r
