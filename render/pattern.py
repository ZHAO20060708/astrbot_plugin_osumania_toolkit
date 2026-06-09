"""Pattern analysis card render (AstrBot html_renderer port)."""
from __future__ import annotations

from typing import Any

from ..helpers import render_template


async def render_pattern_card(data: dict[str, Any]) -> str:
    """Render the pattern card; returns a local PNG path."""
    return await render_template("pattern.html", data)
