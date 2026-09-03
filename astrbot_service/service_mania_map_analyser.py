from __future__ import annotations

import asyncio
import math
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .browser_runtime import ChromiumRenderRuntime, RenderRequest
from .cover_theme import build_cover_theme
from .downloader import download_beatmap_file
from .errors import ManiaMapAnalyserError, NonManiaBeatmapError


_CONTENT_BARS = {"None", "Auto", "Pattern", "Etterna", "Graph", "Full"}
_SR_TEXTS = {"ReworkSR", "MSD", "Pattern", "InterludeSR", "Auto"}
_DIFF_TEXTS = {
    "Difficulty",
    "Graph",
    "MSD",
    "Pattern",
    "ReworkSR",
    "InterludeSR",
    "None",
}
_ESTIMATORS = {"Azusa", "Roxy", "Mixed", "Sunny", "Daniel", "Companella"}
_ETTERNA_VERSIONS = {
    "0.68.0-Unofficial",
    "0.70.0",
    "0.72.0",
    "0.72.3",
    "0.74.0",
    "0.75.0",
}
_CARD_RADII = {"Small", "Medium", "Large"}


def _as_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "是", "开启"}:
            return True
        if normalized in {"false", "0", "no", "off", "否", "关闭"}:
            return False
    return fallback


def _as_choice(value: object, choices: set[str], fallback: str) -> str:
    if value is None:
        return fallback
    normalized = str(value).strip()
    return normalized if normalized in choices else fallback


def _as_css_value(
    value: object,
    pattern: re.Pattern[str],
    fallback: str,
) -> str:
    if value is None:
        return fallback
    normalized = str(value).strip()
    return normalized if pattern.fullmatch(normalized) else fallback


class ManiaMapAnalyserService:
    """把 beatmap 下载、缓存和 Playwright 渲染隔离在 service 层"""

    def __init__(
        self,
        plugin_root: Path,
        plugin_data_path: Path,
        render_config: dict[str, Any],
    ) -> None:
        self.plugin_root = plugin_root
        self.plugin_data_path = plugin_data_path
        self.plugin_data_path.mkdir(parents=True, exist_ok=True)
        self.render_settings = self._normalize_render_settings(render_config)
        self.runtime = ChromiumRenderRuntime(static_root=self.plugin_root)

    def close(self) -> None:
        self.runtime.close()

    def generate_from_bid(
        self,
        bid: str,
        render_overrides: dict[str, Any],
        runtime_overrides: dict[str, Any],
    ) -> dict[str, Any]:
        beatmap_path = download_beatmap_file(
            bid=bid,
            temp_dir=self.plugin_data_path / "osu-download-cache",
        )

        try:
            osu_text = beatmap_path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            raise ManiaMapAnalyserError(f"读取谱面文件失败：{exc}") from exc

        return self._render_osu_text(
            source_name=str(bid),
            osu_text=osu_text,
            render_overrides=render_overrides,
            runtime_overrides=runtime_overrides,
        )

    def generate_from_file(
        self,
        beatmap_path: str | Path,
        render_overrides: dict[str, Any],
        runtime_overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """Render an attached .osu/.mc-converted chart with the same frontend."""

        path = Path(beatmap_path)
        try:
            osu_text = path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            raise ManiaMapAnalyserError(f"读取谱面文件失败：{exc}") from exc

        return self._render_osu_text(
            source_name=path.stem or "chart",
            osu_text=osu_text,
            render_overrides=render_overrides,
            runtime_overrides=runtime_overrides,
        )

    def _render_osu_text(
        self,
        source_name: str,
        osu_text: str,
        render_overrides: dict[str, Any],
        runtime_overrides: dict[str, Any],
    ) -> dict[str, Any]:
        effective_render_settings = dict(self.render_settings)
        effective_render_settings.update(render_overrides)

        effective_runtime = {
            "speedRate": 1.0,
            "odFlag": None,
            "cvtFlag": None,
        }
        effective_runtime.update(runtime_overrides)
        try:
            speed_rate = float(effective_runtime["speedRate"])
        except (TypeError, ValueError):
            speed_rate = 1.0
        if not math.isfinite(speed_rate) or speed_rate <= 0:
            speed_rate = 1.0
        effective_runtime["speedRate"] = speed_rate
        od_flag = effective_runtime.get("odFlag")
        effective_runtime["odFlag"] = str(od_flag).strip() or None if od_flag else None
        cvt_flag = effective_runtime.get("cvtFlag")
        effective_runtime["cvtFlag"] = (
            str(cvt_flag).strip().upper() if cvt_flag else None
        )
        effective_runtime["modSignature"] = (
            f"{effective_runtime['speedRate']:.5f}|"
            f"{effective_runtime['odFlag'] or 'none'}|"
            f"{effective_runtime['cvtFlag'] or 'none'}"
        )

        beatmap_mode = self._extract_beatmap_mode(osu_text)
        if beatmap_mode != 3:
            raise NonManiaBeatmapError(
                f"该谱面不是 osu!mania 谱面，无法分析。当前 Mode: {beatmap_mode}"
            )

        output_dir = self.plugin_data_path / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_name).strip("._") or "chart"
        output_path = output_dir / f"{safe_name}_{uuid4().hex[:16]}.png"
        payload = {
            "osuText": osu_text,
            "settings": effective_render_settings,
            "runtime": effective_runtime,
            "postRenderDelayMs": 700,
        }

        # generate_from_bid() 运行在 asyncio.to_thread 的工作线程里。
        # Python 3.14 起，工作线程默认没有 current event loop，
        # 这里直接用 asyncio.run() 执行一次性的异步封面主题构建。
        try:
            # Cover art is cosmetic. Bound its network work so a dead CDN never
            # consumes the whole chart rendering timeout.
            if effective_render_settings.get("enableCoverArt", True):
                theme = asyncio.run(asyncio.wait_for(
                    build_cover_theme(
                        osu_text=osu_text,
                        cache_dir=self.plugin_data_path / "cover-cache",
                    ),
                    timeout=15,
                ))
            else:
                theme = None
        except Exception:
            theme = None

        if theme:
            payload["theme"] = theme

        self.runtime.render(
            RenderRequest(
                output_path=output_path,
                payload=payload,
                capture_target=effective_render_settings["captureTarget"],
            )
        )

        return {
            "status": "success",
            "msg": f"rendered chart successfully for {source_name}",
            "image_path": str(output_path.resolve()),
        }

    def _extract_beatmap_mode(self, osu_text: str) -> int | None:
        match = re.search(r"(?mi)^\s*Mode\s*:\s*(\d+)\s*$", osu_text)
        return int(match.group(1)) if match else None

    def _normalize_render_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        capture_target = _as_choice(
            config.get("capture_target"), {"full_card", "graph_only"}, "full_card"
        )

        return {
            "captureTarget": capture_target,
            "contentBar": _as_choice(config.get("content_bar"), _CONTENT_BARS, "Auto"),
            "srText": _as_choice(config.get("sr_text"), _SR_TEXTS, "ReworkSR"),
            "diffText": _as_choice(config.get("diff_text"), _DIFF_TEXTS, "Difficulty"),
            "estimatorAlgorithm": _as_choice(
                config.get("estimator_algorithm"), _ESTIMATORS, "Mixed"
            ),
            "etternaVersion": _as_choice(
                config.get("etterna_version"), _ETTERNA_VERSIONS, "0.72.3"
            ),
            "companellaEtternaVersion": _as_choice(
                config.get("companella_etterna_version"), _ETTERNA_VERSIONS, "0.74.0"
            ),
            "enableNumericDifficulty": _as_bool(
                config.get("enable_numeric_difficulty"), True
            ),
            "enableEtternaRainbowBars": _as_bool(
                config.get("enable_etterna_rainbow_bars"), False
            ),
            "showModeTagCapsule": _as_bool(config.get("show_mode_tag_capsule"), True),
            "vibroDetection": _as_bool(config.get("vibro_detection"), True),
            "debugUseAmount": _as_bool(config.get("debug_use_amount"), False),
            "useSvDetection": _as_bool(config.get("debug_use_sv_detection"), True),
            "azusaSunnyReferenceHo": _as_bool(
                config.get("azusa_sunny_reference_ho"), True
            ),
            "cardOpacity": _as_css_value(
                config.get("card_opacity"), re.compile(r"(?:70|80|90|95|100)%"), "95%"
            ),
            "cardBlur": _as_css_value(
                config.get("card_blur"), re.compile(r"(?:Off|\d+px)"), "4px"
            ),
            "cardRadius": _as_choice(config.get("card_radius"), _CARD_RADII, "Medium"),
            "enableCoverArt": _as_bool(config.get("enable_cover_art"), True),
            "enableFloatingTriangles": _as_bool(
                config.get("enable_floating_triangles"), True
            ),
            "customBackgroundColor": _as_css_value(
                config.get("custom_background_color"),
                re.compile(r"#[0-9A-Fa-f]{6}"),
                "#000000",
            ),
            "useOsuFont": _as_bool(config.get("use_osu_font"), True),
        }
