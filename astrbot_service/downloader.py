from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from .errors import ManiaMapAnalyserError


_BID_RE = re.compile(r"^[1-9]\d*$")
_MAX_BEATMAP_BYTES = 64 * 1024 * 1024
_LOCKS_GUARD = threading.Lock()
_DOWNLOAD_LOCKS: dict[Path, threading.Lock] = {}


@contextmanager
def _download_lock(path: Path):
    with _LOCKS_GUARD:
        lock = _DOWNLOAD_LOCKS.setdefault(path, threading.Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _LOCKS_GUARD:
            if not lock.locked() and _DOWNLOAD_LOCKS.get(path) is lock:
                _DOWNLOAD_LOCKS.pop(path, None)


def download_beatmap_file(bid: str, temp_dir: Path) -> Path:
    bid = str(bid).strip()
    if not _BID_RE.fullmatch(bid):
        raise ManiaMapAnalyserError("谱面 ID 无效，请输入正整数 bid")

    temp_dir.mkdir(parents=True, exist_ok=True)
    target_path = temp_dir / f"{bid}.osu"
    with _download_lock(target_path):
        if target_path.is_file() and target_path.stat().st_size > 0:
            return target_path

        request = Request(
            url=f"https://osu.ppy.sh/osu/{bid}",
            headers={"User-Agent": "astrbot-osu-mania-map-analyser/1.0"},
        )

        try:
            with urlopen(request, timeout=20) as response:
                data = response.read(_MAX_BEATMAP_BYTES + 1)
        except HTTPError as exc:
            if exc.code == 404:
                raise ManiaMapAnalyserError(f"未找到 bid {bid} 对应的谱面") from exc
            raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：http {exc.code}") from exc
        except URLError as exc:
            raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：{exc.reason}") from exc
        except (OSError, TimeoutError, ValueError) as exc:
            raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：{exc}") from exc

        if not data:
            raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：返回内容为空")
        if len(data) > _MAX_BEATMAP_BYTES:
            raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：文件超过 64 MiB")

        # Do not leave a partially written cache file visible to another task.
        temporary_path = temp_dir / f".{bid}.{uuid4().hex}.tmp"
        try:
            temporary_path.write_bytes(data)
            os.replace(temporary_path, target_path)
        except OSError as exc:
            raise ManiaMapAnalyserError(f"保存谱面 {bid} 失败：{exc}") from exc
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

        return target_path
