import asyncio
import math
import random
import re
import time
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image as PILImage
from PIL import ImageChops, ImageFilter

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import File, Image, Reply
from astrbot.api.star import Context, Star
from astrbot.core.utils.session_waiter import SessionController, session_waiter

# 导入核心算法
from .algorithm.acc import (
    calculate_acc,
    calculate_acc_change,
    calculate_acc_change_from_dan,
    calculate_acc_from_dan,
    calculate_map_notes,
    get_acc_result_text,
    parse_acc_cmd,
    validate_dan_name,
)
from .algorithm.utils import parse_osu_filename
from .api.osu import download_file_by_id
from .config import apply_plugin_config
from .file.cache import CACHE_DIR
from .file.cleanup import cleanup_old_cache, cleanup_paths
from .handlers.analyze import run_analyze
from .handlers.cvtscore import run_cvtscore
from .handlers.delta_scatter import run_delta, run_scatter
from .handlers.ett import run_ett
from .handlers.mapview import run_mapview
from .handlers.mania_map import run_mania_map
from .handlers.omtk import run_omtk
from .handlers.pattern import run_pattern
from .handlers.percy import run_percy
from .astrbot_service.dependency_bootstrap import bootstrap_plugin_runtime
from .astrbot_service.service_mania_map_analyser import ManiaMapAnalyserService

# 导入 osu!mania 工具箱命令处理器（移植自 nonebot-plugin-osumania-toolkit）
from .handlers.replay_viz import run_lifebar, run_pressingtime, run_spectrum
from .one_last_image import (
    Config as OLIConfig,
)
from .one_last_image import (
    make_diagonal_diff,
    make_side_by_side_diff,
    render_one_last_image,
)


def _coerce_int(value: object, fallback: int) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _coerce_float(
    value: object,
    fallback: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(parsed):
        return fallback
    if minimum is not None and parsed < minimum:
        return fallback
    if maximum is not None and parsed > maximum:
        return fallback
    return parsed


class OsuManiaToolkit(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.plugin_dir = Path(__file__).parent
        self.image_dir = self.plugin_dir / "images"
        self.cache_dir = CACHE_DIR
        self.config = apply_plugin_config(config)
        self.render_service: ManiaMapAnalyserService | None = None
        self.render_startup_error = ""
        self.render_semaphore = asyncio.Semaphore(
            max(1, min(_coerce_int(self.config.max_concurrency, 5), 5))
        )
        self.render_timeout_seconds = _coerce_float(
            self.config.render_timeout_seconds,
            120.0,
            minimum=5.0,
            maximum=900.0,
        )

        # 启动时执行清理逻辑
        max_age = self.config.omtk_cache_max_age
        asyncio.create_task(
            asyncio.to_thread(cleanup_old_cache, CACHE_DIR, max_age_hours=max_age)
        )

    async def initialize(self):
        # 确保自带的 MinaCalc 可执行文件具有执行权限（部分安装/拷贝方式会丢失）。
        runner = self.plugin_dir / "algorithm" / "ett" / "official_minacalc_runner"
        try:
            if runner.exists():
                runner.chmod(0o755)
        except OSError as e:
            logger.warning(f"无法为 MinaCalc runner 添加执行权限: {e}")

        try:
            await asyncio.to_thread(self._initialize_map_renderer)
        except Exception as e:
            self.render_startup_error = str(e)
            logger.exception("ManiaMapAnalyser renderer initialization failed")

    def _initialize_map_renderer(self) -> None:
        bootstrap_plugin_runtime(self.plugin_dir, CACHE_DIR.parent)
        self.render_service = ManiaMapAnalyserService(
            plugin_root=self.plugin_dir,
            plugin_data_path=CACHE_DIR.parent,
            render_config={
                "capture_target": self.config.capture_target,
                "content_bar": self.config.content_bar,
                "sr_text": self.config.sr_text,
                "diff_text": self.config.diff_text,
                "estimator_algorithm": self.config.estimator_algorithm,
                "etterna_version": self.config.etterna_version,
                "companella_etterna_version": self.config.companella_etterna_version,
                "enable_numeric_difficulty": self.config.enable_numeric_difficulty,
                "enable_etterna_rainbow_bars": self.config.enable_etterna_rainbow_bars,
                "show_mode_tag_capsule": self.config.show_mode_tag_capsule,
                "vibro_detection": self.config.vibro_detection,
                "debug_use_amount": self.config.debug_use_amount,
                "debug_use_sv_detection": self.config.debug_use_sv_detection,
                "azusa_sunny_reference_ho": self.config.azusa_sunny_reference_ho,
                "card_opacity": self.config.card_opacity,
                "card_blur": self.config.card_blur,
                "card_radius": self.config.card_radius,
                "enable_cover_art": self.config.enable_cover_art,
                "enable_floating_triangles": self.config.enable_floating_triangles,
                "custom_background_color": self.config.custom_background_color,
                "use_osu_font": self.config.use_osu_font,
            },
        )

    async def terminate(self):
        if self.render_service is not None:
            await asyncio.to_thread(self.render_service.close)
            self.render_service = None

    def add_chromatic_aberration(
        self, image: PILImage.Image, intensity: int = 4
    ) -> PILImage.Image:
        intensity = max(1, min(20, intensity))
        r, g, b = image.split()[:3]

        r_offset = ImageChops.offset(r, -intensity, -intensity)
        g_offset = ImageChops.offset(g, 0, 0)
        b_offset = ImageChops.offset(b, intensity, intensity)

        if len(image.split()) == 4:
            a = image.split()[3]
            return PILImage.merge("RGBA", (r_offset, g_offset, b_offset, a))
        else:
            return PILImage.merge("RGB", (r_offset, g_offset, b_offset))

    def add_glitch_effect(
        self, image: PILImage.Image, intensity: int = 0
    ) -> PILImage.Image:
        intensity = max(0, min(5, intensity))
        if intensity == 0:
            return image.copy()

        width, height = image.size
        glitched = image.copy()

        if intensity >= 1:
            num_shifts = min(3, max(1, intensity))
            for _ in range(num_shifts):
                max_shift = max(5, int(width * 0.1 * intensity / 5))
                shift_amount = random.randint(2, max_shift)
                shift_direction = random.choice([-1, 1])

                min_shift_height = height // 20
                max_shift_height = height // 6 + (height // 12) * (intensity - 1)
                shift_height = random.randint(min_shift_height, max_shift_height)
                shift_y = random.randint(0, height - shift_height)

                region = glitched.crop((0, shift_y, width, shift_y + shift_height))
                glitched.paste(region, (shift_amount * shift_direction, shift_y))

        if intensity >= 2:
            base_noise = 50
            noise_intensity = base_noise * (intensity**2)
            for _ in range(noise_intensity):
                x = random.randint(0, width - 1)
                y = random.randint(0, height - 1)
                color = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                    255,
                )
                glitched.putpixel((x, y), color)

            if intensity >= 3:
                num_blocks = random.randint(1, intensity - 1)
                for _ in range(num_blocks):
                    block_width = random.randint(5, 20)
                    block_height = random.randint(5, 20)
                    block_x = random.randint(0, width - block_width)
                    block_y = random.randint(0, height - block_height)

                    for bx in range(block_width):
                        for by in range(block_height):
                            if random.random() < 0.7:
                                px = min(block_x + bx, width - 1)
                                py = min(block_y + by, height - 1)
                                color = (
                                    random.randint(0, 255),
                                    random.randint(0, 255),
                                    random.randint(0, 255),
                                    255,
                                )
                                glitched.putpixel((px, py), color)

        if intensity >= 3:
            scanline_spacing = random.randint(8 - intensity, 15 - intensity)
            scanline_probability = 0.15 + (intensity - 3) * 0.05

            for y in range(0, height, scanline_spacing):
                if random.random() < scanline_probability:
                    line_height = random.randint(1, 2)
                    line_region = glitched.crop((0, y, width, y + line_height))
                    brightness = 150 + (intensity - 3) * 25
                    line_region = ImageChops.multiply(
                        line_region,
                        PILImage.new(
                            "RGBA",
                            (width, line_height),
                            (brightness, brightness, brightness, 255),
                        ),
                    )
                    glitched.paste(line_region, (0, y))

        if intensity >= 4:
            blur_radius = 0.5 + (intensity - 4) * 0.5
            glitched = glitched.filter(ImageFilter.GaussianBlur(radius=blur_radius))

            if intensity >= 5:
                if len(glitched.split()) >= 3:
                    r, g, b = glitched.split()[:3]
                    offset_x = random.randint(-3, 3)
                    offset_y = random.randint(-3, 3)

                    r_offset = ImageChops.offset(r, offset_x, offset_y)
                    b_offset = ImageChops.offset(b, -offset_x, -offset_y)

                    if len(glitched.split()) == 4:
                        a = glitched.split()[3]
                        glitched = PILImage.merge("RGBA", (r_offset, g, b_offset, a))
                    else:
                        glitched = PILImage.merge("RGB", (r_offset, g, b_offset))

        return glitched

    def resize_greek_image(
        self, greek_img: PILImage.Image, original_width: int, original_height: int
    ) -> PILImage.Image:
        greek_w, greek_h = greek_img.size
        min_original_dimension = min(original_width, original_height)
        target_size = int(min_original_dimension * 1.8)
        scale_ratio = target_size / max(greek_w, greek_h)
        new_width = int(greek_w * scale_ratio)
        new_height = int(greek_h * scale_ratio)
        if new_width < 200:
            new_width = 200
            new_height = int(greek_h * (200 / greek_w))
        return greek_img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

    @filter.command("osugreek")
    async def osugreek_cmd(
        self,
        event: AstrMessageEvent,
        greek_name: str = "",
        chromatic_intensity: int = 4,
        glitch_intensity: int = 0,
    ):
        """生成希腊字母特效图片
        用法: /osugreek <希腊字母名称> [色散强度] [故障强度]
        说明: 支持在命令中附带图片或回复一张图片。
        参数说明:
        - 希腊字母名称: 内置的希腊字母名称（可通过/osugreek help查看）
        - 色散强度: 将图片RGB分离。范围[1,20], 不填则默认4。
        - 故障强度: 将图片应用故障效果。范围[0,5], 不填则默认0。
        """
        if not greek_name or greek_name == "help":
            help_text = "用法：/osugreek <希腊字母名称> [色散强度] [故障强度]\n说明: 支持在命令中附带图片或回复一张图片。\n参数说明: \n- 色散强度: 将图片RGB分离。范围[1,20], 不填则默认4。\n- 故障强度: 将图片应用故障效果。强度决定故障效果的程度。范围[0,5], 不填则默认0。"
            available = [f.stem for f in self.image_dir.glob("*.png")]
            available.sort()
            help_text += f"\n可用的希腊字母名称有: {', '.join(available)}"
            yield event.plain_result(help_text)
            return

        image_component = None

        components_to_check = list(event.message_obj.message)
        for comp in components_to_check:
            if isinstance(comp, Reply) and comp.chain:
                components_to_check.extend(comp.chain)

        for component in components_to_check:
            if isinstance(component, Image):
                image_component = component
                break

        if not image_component:
            yield event.plain_result(
                "请在命令中附带一张图片，或回复包含图片的被引用消息"
            )
            return

        try:
            local_path = await image_component.convert_to_file_path()
            if not local_path:
                yield event.plain_result("图片下载失败: 无法获取图片路径")
                return
            img_data = Path(local_path).read_bytes()
        except Exception as e:
            yield event.plain_result(f"图片下载失败: {e}")
            return

        try:
            original_img = PILImage.open(BytesIO(img_data)).convert("RGBA")

            chromatic_img = self.add_chromatic_aberration(
                original_img, intensity=chromatic_intensity
            )

            if glitch_intensity is not None and glitch_intensity > 0:
                chromatic_img = self.add_glitch_effect(chromatic_img, glitch_intensity)

            greek_img_path = self.image_dir / f"{greek_name}.png"
            if not greek_img_path.exists():
                available = [f.stem for f in self.image_dir.glob("*.png")]
                available.sort()
                yield event.plain_result(
                    f"未找到 {greek_name}.png\n可用的有: {', '.join(available)}"
                )
                return

            greek_img = PILImage.open(greek_img_path).convert("RGBA")
            greek_img = self.resize_greek_image(
                greek_img, original_img.width, original_img.height
            )

            orig_w, orig_h = chromatic_img.size
            greek_w, greek_h = greek_img.size
            x = (orig_w - greek_w) // 2
            y = (orig_h - greek_h) // 2

            combined = PILImage.new("RGBA", chromatic_img.size)
            combined.paste(chromatic_img, (0, 0))
            combined.paste(greek_img, (x, y), greek_img)

            timestamp = int(time.time() * 1000)
            random_suffix = random.randint(1000, 9999)
            temp_filename = f"processed_{timestamp}_{random_suffix}.png"
            temp_output_path = self.cache_dir / temp_filename

            combined.save(temp_output_path, format="PNG")

            yield event.chain_result(
                [Image.fromFileSystem(str(temp_output_path.absolute()))]
            )
        except Exception as e:
            yield event.plain_result(f"图片处理失败: {str(e)}")
            return

    async def _get_reply_file(self, event: AstrMessageEvent):
        for component in event.message_obj.message:
            if isinstance(component, File):
                return getattr(component, "url", None), getattr(
                    component, "name", "file"
                )
        return None, None

    @filter.command("acc")
    async def acc_cmd(self, event: AstrMessageEvent):
        """单曲 ACC 计算"""
        cmd_text = re.sub(
            r"^.*?(?:acc|单曲)(?:\s+|$)",
            "",
            event.message_str.strip(),
            flags=re.IGNORECASE,
        )

        if cmd_text.strip().lower() in ["help"]:
            help_text = (
                "用法: /acc [段位名 | b<谱面ID>] [各曲ACC或当前累计ACC] [-sv2] [-r]\n"
                "说明: 用于计算 osu!mania 组曲(段位)中每一首曲子需要的 ACC 或造成的 ACC 变化。\n"
                "参数说明:\n"
                "- 段位名: 指定预设的段位名称。内置段位命名规则如下：\n"
                "  [danv] Malody 4K Dan (如 1danv2)\n"
                "  [ex] Malody 4K Extra Dan (如 ex1v2)\n"
                "  [spex] Malody 4K Extra Dan v2 (如 spex1)\n"
                "  [rf/reform] 4K Dan ~ REFORM (如 rf1, alpha)\n"
                "  [ln] 4K LN Courses v2 (如 ln1)\n"
                "  [xfpsb] (如 xfpsb1)\n"
                "  [7k] 7K Regular Dan (如 7k1dan)\n"
                "  [7kln] 7K LN Dan (如 7kln1)\n"
                "  [senpai] Senpai Dan v1 (如 senpai1)\n"
                "  [senpaiex] Senpai Dan v1 Extra (如 senpaiex1)\n"
                "  [wds0] wds0 Dan (如 wds0_1)\n"
                "  [misc] 其他附加段位 (如 haku)\n"
                "- b<谱面ID>: 指定组曲谱面ID（也支持 mania 谱面网址）\n"
                "- -sv2: 使用 ScoreV2 计算\n"
                "- -r: 开启反向计算（即通过各首单曲的 ACC 推算最后总体的 ACC 变化）"
            )
            yield event.plain_result(help_text)
            return

        dan_name, acc_str, bid, num_songs, sv2_flag, reverse_flag, error_msg = (
            parse_acc_cmd(cmd_text)
        )
        if error_msg:
            error_text = "\n".join(error_msg)
            yield event.plain_result(f"错误: {error_text}")
            return
        state = {
            "type": "acc",
            "status": "init",
            "acc_str": acc_str,
            "dan_name": dan_name,
            "bid": bid,
            "num_songs": num_songs,
            "sv2_flag": sv2_flag,
            "reverse_flag": reverse_flag,
            "reject_time": 0,
            "mode": None,
        }

        @session_waiter(timeout=60, record_history_chains=False)
        async def acc_waiter(
            controller: SessionController, wait_event: AstrMessageEvent
        ):
            text = wait_event.message_str.strip()
            if text == "0":
                await wait_event.send(wait_event.plain_result("操作已取消。"))
                controller.stop()
                return

            if state.get("type") == "acc":
                if re.match(r"^(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))+$", text):
                    state["acc_str"] = text
                    if state["mode"] in ["predefined", "bid", "custom", "file"]:
                        result = await self._acc_calculate(state)
                        await wait_event.send(wait_event.plain_result(result))
                        controller.stop()
                        return

                if validate_dan_name(text, state.get("sv2_flag")):
                    state["mode"], state["dan_name"] = "predefined", text
                    prompt = "单曲ACC" if state.get("reverse_flag") else "ACC变化"
                    await wait_event.send(
                        wait_event.plain_result(f"已选择段位: {text}\n请输入{prompt}:")
                    )
                    controller.keep(timeout=60, reset_timeout=True)
                    return

            await wait_event.send(
                wait_event.plain_result("输入无效，请重新输入或输入 0 取消。")
            )
            controller.keep(timeout=60, reset_timeout=True)

        if bid:
            state["mode"] = "bid"
            try:
                osu_path, osu_name = await download_file_by_id(CACHE_DIR, bid)
                state["osu_path"] = osu_path
                meta_data = parse_osu_filename(osu_name)
                state["display_name"] = (
                    f"{meta_data['Artist']} - {meta_data['Title']} [{meta_data['Version']}]"
                    if meta_data
                    else osu_name
                )
                note_counts = await calculate_map_notes(osu_path, num_songs, sv2_flag)
                state["note_counts"] = note_counts
                if acc_str:
                    yield event.plain_result(await self._acc_calculate(state))
                else:
                    acc_format = "-".join(
                        [f"acc{i + 1}" for i in range(len(note_counts))]
                    )
                    prompt = "单曲ACC" if reverse_flag else "ACC变化"
                    yield event.plain_result(
                        f"谱面物量分布: {'-'.join(str(n) for n in note_counts)}\n请输入{prompt} (格式: {acc_format}):"
                    )
                    try:
                        await acc_waiter(event)
                    except TimeoutError:
                        yield event.plain_result("操作已超时，会话结束。")
                return
            except Exception as e:
                yield event.plain_result(f"处理谱面时出错: {str(e)}")
                return

        if dan_name:
            state["mode"] = "predefined"
            if acc_str:
                yield event.plain_result(await self._acc_calculate(state))
            else:
                prompt = "单曲ACC" if reverse_flag else "ACC变化"
                yield event.plain_result(f"已选择段位: {dan_name}\n请输入{prompt}:")
                try:
                    await acc_waiter(event)
                except TimeoutError:
                    yield event.plain_result("操作已超时，会话结束。")
            return

    async def _acc_calculate(self, state: dict) -> str:
        try:
            mode, acc_str, sv2_flag, reverse_flag = (
                state["mode"],
                state["acc_str"],
                state.get("sv2_flag", False),
                state.get("reverse_flag", False),
            )
            if mode == "predefined":
                dan_name = state["dan_name"]
                single_accs, err = (
                    calculate_acc_change_from_dan(dan_name, acc_str, sv2_flag)
                    if reverse_flag
                    else calculate_acc_from_dan(dan_name, acc_str, sv2_flag)
                )
                if err:
                    return f"计算错误: {err}"
                return get_acc_result_text(
                    "predefined",
                    dan_name,
                    None,
                    acc_str,
                    single_accs,
                    sv2_flag,
                    reverse_flag,
                )
            elif mode in ["bid", "file", "custom"]:
                note_counts, display_name = (
                    state["note_counts"],
                    state.get("display_name", "未知"),
                )
                single_accs, err = (
                    calculate_acc_change(note_counts, acc_str)
                    if reverse_flag
                    else calculate_acc(note_counts, acc_str, sv2_flag)
                )
                if err:
                    return f"计算错误: {err}"
                return get_acc_result_text(
                    mode,
                    display_name,
                    note_counts,
                    acc_str,
                    single_accs,
                    sv2_flag,
                    reverse_flag,
                )
            return "错误: 未知模式"
        finally:
            await cleanup_paths(
                state.get("osu_path"),
                state.get("downloaded_path"),
                state.get("converted_path"),
            )

    @filter.command("希腊字母")
    async def osugreek_alias(self, event: AstrMessageEvent):
        async for res in self.osugreek_cmd(event):
            yield res

    @filter.command("单曲")
    async def acc_alias(self, event: AstrMessageEvent):
        async for res in self.acc_cmd(event):
            yield res

    # ===== osu!mania 工具箱命令（移植自 nonebot-plugin-osumania-toolkit）=====

    @filter.command("omtk")
    async def omtk_cmd(self, event: AstrMessageEvent):
        """osu!mania 工具箱帮助。用法: /omtk [命令名] [页码]"""
        async for r in run_omtk(self, event):
            yield r

    @filter.command("ma", alias={"mag"})
    async def mania_map_cmd(self, event: AstrMessageEvent):
        """新谱面分析卡片。用法: /ma [模式] <bid> [+dt/+ht/+in/+ho]。"""
        async for r in run_mania_map(self, event):
            yield r

    @filter.command("mapview", alias={"rework"})
    async def mapview_cmd(self, event: AstrMessageEvent):
        """谱面键型分析与难度估计。BID 和单图使用新前端；图包保留批量分析。"""
        async for r in run_mapview(self, event):
            yield r

    @filter.command("ett", alias={"msd"})
    async def ett_cmd(self, event: AstrMessageEvent):
        """计算谱面 Etterna MSD。用法: /ett b<bid> x[speed]，或回复谱面/图包文件"""
        async for r in run_ett(self, event):
            yield r

    @filter.command("pattern", alias={"键型"})
    async def pattern_cmd(self, event: AstrMessageEvent):
        """谱面键型分析。回复 .osu/.mc/.osz/.mcz 文件或 /pattern b<bid>，加 -d 输出详细文本"""
        async for r in run_pattern(self, event):
            yield r

    @filter.command("analyze", alias={"分析", "analyse"})
    async def analyze_cmd(self, event: AstrMessageEvent):
        """回放作弊分析。回复 .osr/.mr 回放，可选 b<bid> 指定谱面，加 -reason 输出详情"""
        async for r in run_analyze(self, event):
            yield r

    @filter.command("delta", alias={"偏差"})
    async def delta_cmd(self, event: AstrMessageEvent):
        """判定偏差柱状图。回复 .osr/.mr 回放并使用 b<bid> 指定谱面"""
        async for r in run_delta(self, event):
            yield r

    @filter.command("scatter", alias={"散点"})
    async def scatter_cmd(self, event: AstrMessageEvent):
        """判定散点图。回复 .osr/.mr 回放并使用 b<bid> 指定谱面"""
        async for r in run_scatter(self, event):
            yield r

    @filter.command("spectrum", alias={"频谱"})
    async def spectrum_cmd(self, event: AstrMessageEvent):
        """回放打击频谱图。回复 .osr/.mr 回放"""
        async for r in run_spectrum(self, event):
            yield r

    @filter.command("lifebar", alias={"血条", "life"})
    async def lifebar_cmd(self, event: AstrMessageEvent):
        """回放血条变化图。回复 .osr 回放"""
        async for r in run_lifebar(self, event):
            yield r

    @filter.command("pressingtime", alias={"按压"})
    async def pressingtime_cmd(self, event: AstrMessageEvent):
        """回放按键时间分析。回复 .osr/.mr 回放"""
        async for r in run_pressingtime(self, event):
            yield r

    @filter.command("percy", alias={"投皮"})
    async def percy_cmd(self, event: AstrMessageEvent):
        """LN 投皮修改。回复 .png 面身图片，用法: /percy [目标程度] [lazer]"""
        async for r in run_percy(self, event):
            yield r

    @filter.command("cvtscore", alias={"转换"})
    async def cvtscore_cmd(self, event: AstrMessageEvent):
        """成绩转换。/cvtscore [bid] [目标ruleset] [-sv2]，随后按提示发送回放与谱面"""
        async for r in run_cvtscore(self, event):
            yield r

    @filter.command("oli")
    async def oli_cmd(self, event: AstrMessageEvent):
        """生成 One Last Image 特效图片
        用法: /oli [模式(normal/diff/diff2)] [参数=值 ...]
        说明: 支持在命令中附带图片或回复一张图片。
        参数说明:
        - 模式: normal (默认), diff (上下对比), diff2 (对角线对比)
        可选参数 (示例: zoom=1.2 watermark=False):
        zoom(浮点), cover(布尔), light(浮点), shade(布尔), kuma(布尔), watermark(布尔),
        hajimei(布尔), convolute_name(字符: 精细/一般/稍粗...), denoise(布尔), invert_color(布尔), bevel_position(整数)
        """
        cmd_text = re.sub(
            r"^.*?(?:oli)(?:\s+|$)", "", event.message_str.strip(), flags=re.IGNORECASE
        ).strip()
        args = cmd_text.split()

        mode = "normal"
        if args and args[0] in ["normal", "diff", "diff2", "help"]:
            mode = args[0]
            args = args[1:]
        elif args and "=" not in args[0]:
            mode = args[0]
            args = args[1:]

        if mode == "help" or (
            mode not in ["normal", "diff", "diff2"] and not mode.startswith("help")
        ):
            help_text = (
                "用法: /oli [模式(normal/diff/diff2)] [参数=值 ...]\n"
                "说明: 生成《Evangelion: 3.0+1.0》One Last Kiss 风格渐变海报/线稿，支持在命令中附带图片或回复一张图片。\n"
                "参数说明:\n"
                "- 模式: normal (默认), diff (上下对比), diff2 (对角线对比)\n"
                "- 可选参数(格式 参数=值):\n"
                "  zoom(缩放倍数), cover(是否居中裁剪),\n"
                "  light(亮度补偿), shade(启用阴影), kuma(启用渐变色),\n"
                "  watermark(开启水印), hajimei(特殊水印裁剪),\n"
                "  convolute_name(线稿画笔粗细: 精细/一般/稍粗/超粗/极粗/浮雕/线稿),\n"
                "  denoise(开启降噪), invert_color(反色), bevel_position(对角线截断位置, 默认20)\n"
                "示例: /oli diff2 invert_color=True watermark=False convolute_name=稍粗"
            )
            yield event.plain_result(help_text)
            return

        image_component = None

        components_to_check = list(event.message_obj.message)
        for comp in components_to_check:
            if isinstance(comp, Reply) and comp.chain:
                components_to_check.extend(comp.chain)

        for component in components_to_check:
            if isinstance(component, Image):
                image_component = component
                break

        if not image_component:
            yield event.plain_result(
                "请在命令中附带一张图片，或回复包含图片的被引用消息"
            )
            return

        try:
            local_path = await image_component.convert_to_file_path()
            if not local_path:
                yield event.plain_result("图片下载失败: 无法获取图片路径")
                return
            img_data = Path(local_path).read_bytes()
        except Exception as e:
            yield event.plain_result(f"图片下载失败: {e}")
            return

        try:
            original_img = PILImage.open(BytesIO(img_data)).convert("RGBA")

            # 解析附加参数
            kw = {}
            for arg in args:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    if v.lower() in ("true", "t", "1", "yes"):
                        v = True
                    elif v.lower() in ("false", "f", "0", "no"):
                        v = False
                    elif k in ("zoom", "light"):
                        v = float(v)
                    elif k in (
                        "shade_limit",
                        "shade_light",
                        "light_cut",
                        "dark_cut",
                        "bevel_position",
                    ) or (k == "seed" and v):
                        v = int(v)
                    kw[k] = v
            try:
                config = OLIConfig(**kw)
            except Exception as e:
                yield event.plain_result(f"参数提取或验证错误: {e}")
                return

            # 图片处理涉及大量矩阵运算，使用 to_thread 放入线程池，防止阻塞机器人异步事件循环导致掉线或被 Kill
            rendered = await asyncio.to_thread(
                render_one_last_image, original_img, config
            )

            if mode == "diff":
                final_image = await asyncio.to_thread(
                    make_side_by_side_diff, rendered, original_img
                )
            elif mode == "diff2":
                final_image = await asyncio.to_thread(
                    make_diagonal_diff, rendered, original_img, config.bevel_position
                )
            else:
                final_image = rendered

            timestamp = int(time.time() * 1000)
            random_suffix = random.randint(1000, 9999)
            temp_filename = f"oli_{timestamp}_{random_suffix}.png"
            temp_output_path = self.cache_dir / temp_filename

            final_image.save(temp_output_path, format="PNG")

            yield event.chain_result(
                [Image.fromFileSystem(str(temp_output_path.absolute()))]
            )
        except Exception as e:
            yield event.plain_result(f"图片处理失败: {str(e)}")
            return
