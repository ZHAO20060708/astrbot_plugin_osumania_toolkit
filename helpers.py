"""Shared adaptation seams between the ported osu!mania toolkit logic and AstrBot.

The upstream NoneBot plugin received files via OneBot `get_file` APIs, sent images
with `MessageSegment.image`, rendered HTML via `nonebot_plugin_htmlkit.template_to_pic`,
and sent merged-forward messages via OneBot forward APIs. This module re-implements
those three seams against AstrBot's primitives so the handlers can stay close to the
original matcher logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator, Optional, Sequence, Union

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import (
    BaseMessageComponent,
    File,
    Image,
    Node,
    Nodes,
    Plain,
    Reply,
)
from astrbot.core import html_renderer

from .config import Config, get_plugin_config

_config = get_plugin_config(Config)
_TEMPLATE_DIR = Path(__file__).resolve().parent / "render" / "templates"

# Platforms whose adapters render OneBot-style merged-forward (Nodes) messages.
_FORWARD_PLATFORMS = {"aiocqhttp"}

ForwardItem = Union[str, Sequence[BaseMessageComponent]]


def _max_file_size_bytes() -> int:
    mb = getattr(_config, "max_file_size_mb", 0)
    return mb * 1024 * 1024 if mb and mb > 0 else 0


def _iter_components(event: AstrMessageEvent) -> list[BaseMessageComponent]:
    """All components of the current message plus any quoted (Reply) message."""
    comps: list[BaseMessageComponent] = list(event.message_obj.message)
    expanded: list[BaseMessageComponent] = []
    for comp in comps:
        if isinstance(comp, Reply) and comp.chain:
            expanded.extend(comp.chain)
    # Quoted message first (commands are usually "reply to a file"), then current.
    return expanded + comps


async def get_attached_file(
    event: AstrMessageEvent,
    exts: tuple[str, ...],
    include_image: bool = False,
) -> Optional[tuple[Path, str]]:
    """Locate a File (optionally Image) attachment in the message or its reply.

    Returns (local_path, display_name) or None if no matching attachment is found.
    Raises ValueError on extension/size validation failure so callers can surface a
    precise message to the user.
    """
    exts = tuple(e.lower() for e in exts)
    max_size = _max_file_size_bytes()

    for comp in _iter_components(event):
        if isinstance(comp, File):
            name = os.path.basename((comp.name or "file").replace("\\", "/"))
            if exts and not name.lower().endswith(exts):
                raise ValueError(f"请回复 {('/'.join(exts))} 格式的文件。")
            local = await comp.get_file()
            if not local or not os.path.exists(local):
                return None
            path = Path(local)
            if max_size and path.stat().st_size > max_size:
                raise ValueError(
                    f"文件过大，超过 {_config.max_file_size_mb} MB 限制。"
                )
            return path, name

        if include_image and isinstance(comp, Image):
            local = await comp.convert_to_file_path()
            if not local or not os.path.exists(local):
                return None
            name = os.path.basename(local)
            if exts and not name.lower().endswith(exts):
                raise ValueError(
                    f"请回复 {('/'.join(exts))} 格式的图片（建议以文件形式发送以避免压缩）。"
                )
            return Path(local), name

    return None


async def render_template(
    template_name: str,
    data: dict,
    options: dict | None = None,
    return_url: bool = False,
) -> str:
    """Render a Jinja2 HTML template from render/templates/ to an image.

    Returns a local file path (return_url=False) or a URL (return_url=True). The
    templates carry fixed pixel widths in CSS, so the renderer's default full-page
    screenshot reproduces the upstream layout. PNG is forced for the glass-style cards.
    """
    tmpl_str = (_TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
    opts = {"type": "png", "full_page": True}
    if options:
        opts.update(options)
    return await html_renderer.render_custom_template(
        tmpl_str, data, return_url=return_url, options=opts
    )


async def forward_results(
    event: AstrMessageEvent,
    items: list[ForwardItem],
    nickname: str = "osu!mania toolkit",
) -> AsyncGenerator:
    """Yield results presenting `items` as a merged-forward message.

    Each item is either a text string or a list of message components. On OneBot
    platforms a single Nodes (forward) message is produced; elsewhere each item is
    sent as a separate message (forward isn't universally supported).
    """
    if not items:
        return

    self_id = event.get_self_id() or "0"
    nodes: list[Node] = []
    for item in items:
        content = [Plain(item)] if isinstance(item, str) else list(item)
        nodes.append(Node(content=content, name=nickname, uin=str(self_id)))

    if event.get_platform_name() in _FORWARD_PLATFORMS:
        yield event.chain_result([Nodes(nodes)])
    else:
        for node in nodes:
            yield event.chain_result(list(node.content))
