"""Mapview difficulty card render (AstrBot html_renderer port).

Replaces the upstream nonebot_plugin_htmlkit `template_to_pic` wrapper. The card's
size is fixed in the template CSS, so a full-page screenshot reproduces the layout.
"""
from __future__ import annotations

from ..helpers import render_template


async def render_analysis_card(data: dict) -> str:
    """Render the mapview analysis card; returns a local PNG path."""
    return await render_template("mapview.html", data)
