"""Etterna MSD card render (AstrBot html_renderer port)."""
from __future__ import annotations

from ..helpers import render_template


async def render_ett_card(data: dict) -> str:
    """Render the ETT skillset card; returns a local PNG path."""
    return await render_template("ett.html", data)
