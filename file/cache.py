from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

PLUGIN_NAME = "astrbot_plugin_osumania_toolkit"
PLUGIN_DATA_DIR = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
CACHE_DIR = PLUGIN_DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
