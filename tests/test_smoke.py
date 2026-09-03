import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PLUGINS_PARENT = PLUGIN_DIR.parent
if str(PLUGINS_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGINS_PARENT))

vendor_dir = Path("/AstrBot/data/plugin_data/astrbot_plugin_osumania_toolkit/runtime/site-packages")
if vendor_dir.exists() and str(vendor_dir) not in sys.path:
    sys.path.insert(0, str(vendor_dir))
browser_dir = Path("/AstrBot/data/plugin_data/astrbot_plugin_osumania_toolkit/runtime/ms-playwright")
if browser_dir.exists():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)

SAMPLE_OSU_CONTENT = """osu file format v14

[General]
AudioFilename: audio.mp3
AudioLeadIn: 0
Mode: 3

[Metadata]
Title:Test Song
Artist:Test Artist
Creator:Test Mapper
Version:Normal

[Difficulty]
CircleSize:4
OverallDifficulty:8

[TimingPoints]
0,500,4,2,0,50,1,0

[HitObjects]
64,192,1000,1,0,0:0:0:0:
192,192,1500,1,0,0:0:0:0:
320,192,2000,1,0,0:0:0:0:
448,192,2500,1,0,0:0:0:0:
64,192,3000,128,0,3500:0:0:0:0:
"""


class TestSmoke(unittest.TestCase):
    def test_data_decoupling(self):
        """Verify data.py re-exports all decoupled data objects and types."""
        from astrbot_plugin_osumania_toolkit.data import (
            dan_data,
            estimator_data,
            file_parser_data,
            omtk_help_data,
            sr_color,
            sr_intervals_data,
        )
        from astrbot_plugin_osumania_toolkit.data_estimator import estimator_data as direct_estimator_data
        from astrbot_plugin_osumania_toolkit.data_dan import dan_data as direct_dan_data
        from astrbot_plugin_osumania_toolkit.data_intervals import sr_intervals_data as direct_intervals

        # Check estimator data
        self.assertIn("rcLnRatioLimit", estimator_data.AZUSA_CONFIG)
        self.assertGreater(len(estimator_data.AZUSA_ISOTONIC_POINTS), 50)
        self.assertEqual(estimator_data.AZUSA_CONFIG, direct_estimator_data.AZUSA_CONFIG)
        self.assertEqual(len(estimator_data.AZUSA_ISOTONIC_POINTS), len(direct_estimator_data.AZUSA_ISOTONIC_POINTS))

        # Check dan data
        self.assertIn("1danv2", dan_data.dan_notes)
        self.assertIn("alpha", dan_data.dan_notes)
        self.assertEqual(dan_data.dan_notes, direct_dan_data.dan_notes)

        # Check intervals data
        self.assertGreater(len(sr_intervals_data.LN_intervals_4K), 10)
        self.assertEqual(sr_intervals_data.LN_intervals_4K, direct_intervals.LN_intervals_4K)

        # Check sr_color
        sc = sr_color()
        bg = sc._color_for(5.5, sc.STAR_BG_STOPS, "#6d7894")
        text_pref = sc._color_for(5.5, sc.STAR_TEXT_STOPS, "#f6fbff")
        text = sc._pick_readable_text_color(5.5, bg, text_pref)
        self.assertTrue(bg.startswith("#"))
        self.assertTrue(text.startswith("#"))

        # Check omtk_help_data
        self.assertGreater(len(omtk_help_data.help_text), 0)

    def test_acc_calculation(self):
        """Verify accuracy calculation and command parsing."""
        from astrbot_plugin_osumania_toolkit.algorithm.acc import calculate_acc, parse_acc_cmd

        # Test calculate_acc with note counts and acc string
        single_accs, err = calculate_acc([1000, 1000, 1000, 1000], "98.0-97.0-96.0-95.0")
        self.assertIsNone(err)
        self.assertEqual(len(single_accs), 4)

        # Parse acc command
        dan_name, acc_str, bid, num_songs, sv2, rev, errs = parse_acc_cmd("b123456 98.0-97.0-96.0-95.0")
        self.assertEqual(bid, 123456)
        self.assertEqual(acc_str, "98.0-97.0-96.0-95.0")

    def test_osu_parser(self):
        """Verify .osu parser correctly reads 4K mania charts."""
        from astrbot_plugin_osumania_toolkit.parser.osu_file_parser import osu_file

        with tempfile.NamedTemporaryFile("w", suffix=".osu", delete=False) as f:
            f.write(SAMPLE_OSU_CONTENT)
            f.flush()
            temp_path = f.name

        try:
            chart = osu_file(temp_path)
            chart.process()
            self.assertEqual(chart.status, "OK")
            self.assertEqual(chart.column_count, 4)
            self.assertEqual(len(chart.note_starts), 5)
            self.assertEqual(chart.GameMode, "3")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_lazy_browser_runtime(self):
        """Verify ChromiumRenderRuntime does not start Chromium or HTTP server at initialization."""
        from astrbot_plugin_osumania_toolkit.astrbot_service.browser_runtime import ChromiumRenderRuntime

        runtime = ChromiumRenderRuntime(static_root=PLUGIN_DIR, idle_timeout_seconds=30)
        try:
            # Must be ready to receive jobs immediately
            self.assertTrue(runtime._ready.is_set())
            # Browser and context must NOT be launched eagerly
            self.assertIsNone(runtime._browser, "Chromium was eagerly started!")
            self.assertIsNone(runtime._context, "Browser context was eagerly started!")
            self.assertIsNone(runtime._static_server, "Static server was eagerly started!")
        finally:
            runtime.close()

    def test_etterna_version_support(self):
        """Verify Etterna 0.75.0 is included in supported versions."""
        from astrbot_plugin_osumania_toolkit.astrbot_service.service_mania_map_analyser import _ETTERNA_VERSIONS

        self.assertIn("0.75.0", _ETTERNA_VERSIONS)
        self.assertIn("0.72.3", _ETTERNA_VERSIONS)

    def test_companella_lazy_ort(self):
        """Verify companella module can be imported without instantiating onnx session."""
        from astrbot_plugin_osumania_toolkit.algorithm.estimator import companella

        self.assertIsNone(companella._SESSION)
        self.assertTrue(hasattr(companella, "classify_companella_difficulty"))

    def test_card_render_e2e(self):
        """Verify end-to-end beatmap card screenshot generation with synced frontend."""
        from astrbot_plugin_osumania_toolkit.astrbot_service.service_mania_map_analyser import ManiaMapAnalyserService

        with tempfile.NamedTemporaryFile("w", suffix=".osu", delete=False) as f:
            f.write(SAMPLE_OSU_CONTENT)
            f.flush()
            temp_path = Path(f.name)

        temp_cache = Path(tempfile.mkdtemp(prefix="ma_smoke_"))
        service = ManiaMapAnalyserService(
            plugin_root=PLUGIN_DIR,
            plugin_data_path=temp_cache,
            render_config={
                "content_bar": "Auto",
                "sr_text": "ReworkSR",
                "diff_text": "Difficulty",
                "estimator_algorithm": "Mixed",
                "etterna_version": "0.72.3",
                "companella_etterna_version": "0.74.0",
                "enable_numeric_difficulty": True,
                "enable_etterna_rainbow_bars": False,
                "show_mode_tag_capsule": True,
                "vibro_detection": True,
                "debug_use_amount": False,
                "use_sv_detection": True,
                "azusa_sunny_reference_ho": True,
                "card_opacity": "95%",
                "card_blur": "4px",
                "card_radius": "Medium",
                "enable_cover_art": False,
                "enable_floating_triangles": False,
                "custom_background_color": "#000000",
                "use_osu_font": True,
            },
        )
        try:
            result = service.generate_from_file(
                temp_path,
                render_overrides={},
                runtime_overrides={"speedRate": 1.0, "odFlag": False},
            )
            self.assertEqual(result.get("status"), "success")
            img_path = Path(result["image_path"])
            self.assertTrue(img_path.exists())
            self.assertGreater(img_path.stat().st_size, 1000)
        finally:
            service.close()
            temp_path.unlink(missing_ok=True)
            import shutil
            shutil.rmtree(temp_cache, ignore_errors=True)

    def test_chart_clone(self):
        """Verify osu_file.clone() produces an independent copy of collections."""
        from astrbot_plugin_osumania_toolkit.parser.osu_file_parser import osu_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".osu", delete=False) as f:
            f.write(SAMPLE_OSU_CONTENT)
            temp_path = Path(f.name)
        try:
            chart = osu_file(str(temp_path))
            chart.process()
            self.assertEqual(chart.status, "OK")
            self.assertEqual(chart.column_count, 4)

            cloned = chart.clone()
            self.assertEqual(cloned.status, "OK")
            self.assertEqual(cloned.column_count, 4)
            self.assertEqual(len(cloned.columns), len(chart.columns))

            # Modify clone collections and verify independence
            cloned.columns.append(99)
            self.assertNotEqual(len(cloned.columns), len(chart.columns))
        finally:
            temp_path.unlink(missing_ok=True)

    def test_roxy_estimator(self):
        """Verify Roxy RC estimator executes successfully and returns valid dictionary."""
        from astrbot_plugin_osumania_toolkit.algorithm.estimator.roxy import estimate_roxy_result
        lines = [
            "osu file format v14\n\n[General]\nMode: 3\n\n[Difficulty]\nCircleSize: 4\nOverallDifficulty: 8\n\n[TimingPoints]\n0,500,4,2,0,50,1,0\n\n[HitObjects]\n"
        ]
        for i in range(100):
            col = (i % 4) * 128 + 64
            t = 1000 + i * 200
            lines.append(f"{col},192,{t},1,0,0:0:0:0:\n")
        roxy_chart = "".join(lines)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".osu", delete=False) as f:
            f.write(roxy_chart)
            temp_path = Path(f.name)
        try:
            result = estimate_roxy_result(temp_path, speed_rate=1.0)
            self.assertIn("estDiff", result)
            self.assertIn("numericDifficulty", result)
            self.assertIn("star", result)
            self.assertEqual(result.get("columnCount"), 4)
            self.assertTrue(result.get("estDiff"))
        finally:
            temp_path.unlink(missing_ok=True)

    def test_ett_cache(self):
        """Verify compute_difficulties caches results by chart content fingerprint."""
        from astrbot_plugin_osumania_toolkit.parser.osu_file_parser import osu_file
        from astrbot_plugin_osumania_toolkit.algorithm.ett.calc import (
            compute_difficulties,
            _difficulties_cache_get,
            _build_difficulties_cache_key,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".osu", delete=False) as f:
            f.write(SAMPLE_OSU_CONTENT)
            temp_path = Path(f.name)
        try:
            chart = osu_file(str(temp_path))
            chart.process()
            res1 = compute_difficulties(chart, music_rate=1.0, keycount=4)
            cache_key = _build_difficulties_cache_key(chart, 1.0, 4, 0.93)
            cached = _difficulties_cache_get(cache_key)
            self.assertIsNotNone(cached)
            self.assertEqual(res1, cached)

            res2 = compute_difficulties(chart, music_rate=1.0, keycount=4)
            self.assertEqual(res1, res2)
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
