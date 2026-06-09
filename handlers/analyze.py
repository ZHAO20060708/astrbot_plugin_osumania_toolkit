"""Replay-integrity (anti-cheat) analysis command: /analyze.

Requires a replied .osr/.mr replay. If a beatmap id is supplied it runs the full
chart-aware analysis immediately; otherwise it interactively asks for a chart file
(or "1" to analyse without a chart, "0" to cancel) via a session waiter.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.utils.session_waiter import session_waiter, SessionController

from ..file.cache import CACHE_DIR
from ..file.cleanup import cleanup_temp_file
from ..parser.osr_file_parser import osr_file
from ..parser.osu_file_parser import osu_file
from ..parser.mr_file_parser import mr_file
from ..api.osu import download_file_by_id
from ..algorithm.utils import parse_cmd, parse_bid_or_url, is_mc_file
from ..algorithm.conversion import convert_mr_to_osr, convert_mc_to_osu
from ..algorithm.detector import run_analyze_cheating, format_analyze_result
from ..render.comprehensive import run_plot_comprehensive
from ..helpers import get_attached_file


async def _compute(osr, osu, show_reason: bool) -> tuple[str, str]:
    output_path = await run_plot_comprehensive(str(CACHE_DIR), osr, osu)
    result = await run_analyze_cheating(osr, osu)
    return output_path, format_analyze_result(result, show_reason)


async def _load_chart(path: Path, file_name: str):
    chart_file = path
    if is_mc_file(str(path)):
        osu_file_path = await asyncio.to_thread(convert_mc_to_osu, str(path), str(CACHE_DIR))
        chart_file = Path(osu_file_path)
    osu = await asyncio.to_thread(osu_file, str(chart_file))
    await asyncio.to_thread(osu.process)
    return osu


async def run_analyze(plugin, event: AstrMessageEvent):
    cmd_text = event.message_str.strip()
    show_reason = "-reason" in cmd_text.lower()
    *_, bid, _md, cmd_err = parse_cmd(cmd_text)
    if cmd_err:
        yield event.plain_result("错误:\n" + "\n".join(cmd_err) + "\n请检查命令格式并重试。")
        return

    try:
        found = await get_attached_file(event, (".osr", ".mr"))
    except ValueError as e:
        yield event.plain_result(str(e))
        return
    if not found:
        yield event.plain_result("请回复一条包含回放文件的消息，或使用 b<谱面ID> 指定谱面。")
        return
    osr_path, file_name = found

    try:
        if file_name.lower().endswith(".mr"):
            mr_obj = await asyncio.to_thread(mr_file, osr_path)
            osr = await asyncio.to_thread(convert_mr_to_osr, mr_obj)
        else:
            osr = await asyncio.to_thread(osr_file, osr_path)
            await asyncio.to_thread(osr.process)
        if osr.status == "NotMania":
            yield event.plain_result("该回放不是 Mania 模式。")
            return
        if osr.status == "tooFewKeys":
            yield event.plain_result("有效轨道数量过少，无法分析。")
            return
        if osr.status == "init":
            yield event.plain_result("回放尚未process。")
            return
    except Exception as e:
        yield event.plain_result(f"处理过程中发生错误：{type(e).__name__}: {e}")
        return

    # --- bid supplied: analyse immediately ---
    if bid is not None:
        osu_path = None
        output_path = None
        try:
            osu_path, _ = await download_file_by_id(CACHE_DIR, bid)
            osu = await asyncio.to_thread(osu_file, str(osu_path))
            await asyncio.to_thread(osu.process)
            if osu.status == "NotMania":
                yield event.plain_result("该谱面不是 Mania 模式。")
                return
            if osu.status == "init":
                yield event.plain_result("谱面尚未process。")
                return
            yield event.plain_result("已收到文件，请稍候...")
            output_path, text = await _compute(osr, osu, show_reason)
            yield event.chain_result([Image.fromFileSystem(output_path)])
            yield event.plain_result(text)
        except Exception as e:
            yield event.plain_result(str(e))
        finally:
            if osu_path and Path(osu_path).exists():
                asyncio.create_task(cleanup_temp_file(Path(osu_path)))
            if output_path and Path(output_path).exists():
                asyncio.create_task(cleanup_temp_file(Path(output_path)))
        return

    # --- no bid: interactive ---
    yield event.plain_result(
        "未提供谱面 ID, 请发送对应的谱面文件。输入 1 跳过（将执行无谱面分析），输入 0 取消。"
    )

    @session_waiter(timeout=120, record_history_chains=False)
    async def waiter(controller: SessionController, wait_event: AstrMessageEvent):
        text = wait_event.message_str.strip()
        wrong_ext = False
        chart = None
        try:
            chart = await get_attached_file(wait_event, (".osu", ".mc"))
        except ValueError:
            wrong_ext = True

        osu_path = None
        output_path = None
        try:
            if wrong_ext:
                await wait_event.send(wait_event.plain_result("请发送 .osu 或 .mc 格式的谱面文件。"))
                controller.keep(timeout=120, reset_timeout=True)
                return

            if chart is not None:
                chart_path, _name = chart
                osu = await _load_chart(chart_path, _name)
            elif text == "0":
                await wait_event.send(wait_event.plain_result("操作已取消。"))
                controller.stop()
                return
            elif text == "1":
                await wait_event.send(wait_event.plain_result("处理中，请稍后..."))
                output_path, result_text = await _compute(osr, None, show_reason)
                await wait_event.send(wait_event.chain_result([Image.fromFileSystem(output_path)]))
                await wait_event.send(wait_event.plain_result(result_text))
                controller.stop()
                return
            elif text:
                parsed_bid, bid_err = parse_bid_or_url(text)
                if bid_err is not None or parsed_bid is None:
                    await wait_event.send(wait_event.plain_result(
                        (bid_err or "输入无效") + "\n请发送谱面文件，或输入 b<bid>/mania 链接，输入 1 跳过，输入 0 取消。"
                    ))
                    controller.keep(timeout=120, reset_timeout=True)
                    return
                osu_path, _ = await download_file_by_id(CACHE_DIR, int(parsed_bid))
                osu = await asyncio.to_thread(osu_file, str(osu_path))
                await asyncio.to_thread(osu.process)
            else:
                await wait_event.send(wait_event.plain_result(
                    "输入无效，请发送谱面文件，或输入 1 跳过，输入 0 取消。"
                ))
                controller.keep(timeout=120, reset_timeout=True)
                return

            if osu.status == "NotMania":
                await wait_event.send(wait_event.plain_result("该谱面不是 Mania 模式。"))
                controller.stop()
                return
            if osu.status == "init":
                await wait_event.send(wait_event.plain_result("谱面尚未process。"))
                controller.stop()
                return

            await wait_event.send(wait_event.plain_result("已收到，处理中，请稍候..."))
            output_path, result_text = await _compute(osr, osu, show_reason)
            await wait_event.send(wait_event.chain_result([Image.fromFileSystem(output_path)]))
            await wait_event.send(wait_event.plain_result(result_text))
            controller.stop()
        except Exception as e:
            await wait_event.send(wait_event.plain_result(f"错误：{e}"))
            controller.stop()
        finally:
            if osu_path and Path(osu_path).exists():
                asyncio.create_task(cleanup_temp_file(Path(osu_path)))
            if output_path and Path(output_path).exists():
                asyncio.create_task(cleanup_temp_file(Path(output_path)))

    try:
        await waiter(event)
    except TimeoutError:
        yield event.plain_result("操作已超时，会话结束。")
    finally:
        if osr_path and Path(osr_path).exists():
            asyncio.create_task(cleanup_temp_file(Path(osr_path)))
