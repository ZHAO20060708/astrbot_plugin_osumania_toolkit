"""Command handler implementations for the osu!mania toolkit.

Each module exposes an async-generator ``run_*(plugin, event)`` that yields AstrBot
results; the thin ``@filter.command`` methods in ``main.py`` delegate to these.
"""
