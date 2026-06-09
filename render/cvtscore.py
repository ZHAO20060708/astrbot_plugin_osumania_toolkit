"""Score-conversion card render (AstrBot html_renderer port)."""
from __future__ import annotations

from typing import Any

from ..helpers import render_template


async def render_cvtscore_card(data: dict[str, Any]) -> str:
    """Render the cvtscore card; returns a local PNG path."""
    return await render_template("cvtscore.html", data)
