import os
from pathlib import Path

# 在插件目录下创建一个 cache 文件夹
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
