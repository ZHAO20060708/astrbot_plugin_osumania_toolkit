"""Score conversion: /cvtscore (alias /转换).

Recompute a replay's score under a target ruleset. Inputs: replay (.osr/.mr) +
chart (bid or .osu/.mc) + target ruleset. Drives a multi-stage interactive flow
(need_replay -> need_chart -> need_ruleset) via a session waiter, mirroring the
upstream got()/reject() state machine.
"""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Image
from astrbot.core.utils.session_waiter import session_waiter, SessionController

from ..file.cache import CACHE_DIR
from ..algorithm.scoring.state import (
    cleanup_cvtscore_state,
    load_chart_from_path,
    load_replay_from_path,
    prepare_cvtscore_state,
    run_cvtscore_conversion,
    update_cvtscore_state_from_text_input,
)
from ..algorithm.scoring.ruleset import get_ruleset_quick_help_text, parse_cvtscore_cmd
from ..algorithm.utils import parse_bid_or_url
from ..render.cvtscore import render_cvtscore_card
from ..helpers import get_attached_file

_REPLAY_EXTS = (".osr", ".mr")
_CHART_EXTS = (".osu", ".mc")
_ALL_EXTS = _REPLAY_EXTS + _CHART_EXTS


def _new_state() -> dict:
    return {
        "status": "init", "reject_time": 0, "bid_loaded": False, "bid_load_error": None,
        "bid": None, "force_sv2": None, "target_spec": None, "replay_kind": None,
        "replay_path": None, "replay_name": None, "osr_obj": None, "mr_obj": None,
        "chart_path": None, "chart_name": None, "osu_obj": None,
        "downloaded_chart_path": None, "converted_chart_path": None,
    }


async def _build_result_messages(ev: AstrMessageEvent, payload: dict | None) -> list:
    payload = payload or {}
    text = str(payload.get("text") or "转换完成。")
    card_data = payload.get("card_data")
    if isinstance(card_data, dict):
        try:
            img_path = await render_cvtscore_card(card_data)
            return [ev.chain_result([Image.fromFileSystem(img_path)])]
        except Exception:
            logger.exception("cvtscore card render failed")
    return [ev.plain_result(text)]


async def _load_replied_file(event: AstrMessageEvent, state: dict) -> str | None:
    """Load a replied replay or chart file (dispatched by extension). Returns an
    error string, or None (no file found / loaded OK)."""
    try:
        found = await get_attached_file(event, _ALL_EXTS)
    except ValueError:
        return "回复消息中的文件既不是有效回放也不是有效谱面。"
    if not found:
        return None
    path, name = found
    if name.lower().endswith(_REPLAY_EXTS):
        return await load_replay_from_path(path, name, state, CACHE_DIR)
    return await load_chart_from_path(path, name, state, CACHE_DIR)


async def run_cvtscore(plugin, event: AstrMessageEvent):
    state = _new_state()
    bid, force_sv2, ruleset_spec, cmd_errors = parse_cvtscore_cmd(event.message_str.strip())
    if cmd_errors:
        await cleanup_cvtscore_state(state)
        yield event.plain_result("错误:\n" + "\n".join(cmd_errors))
        return
    state["bid"] = bid
    state["force_sv2"] = force_sv2
    state["target_spec"] = ruleset_spec

    try:
        load_err = await _load_replied_file(event, state)
        if load_err and (state["osr_obj"] is None and state["osu_obj"] is None):
            await cleanup_cvtscore_state(state)
            yield event.plain_result(load_err)
            return

        ready, prompt = await prepare_cvtscore_state(state, CACHE_DIR)
        if ready:
            payload, err = await run_cvtscore_conversion(state)
            await cleanup_cvtscore_state(state)
            if err:
                yield event.plain_result(f"转换失败: {err}")
                return
            for m in await _build_result_messages(event, payload):
                yield m
            return
    except Exception as exc:
        await cleanup_cvtscore_state(state)
        yield event.plain_result(f"处理失败: {exc}")
        return

    # --- interactive ---
    yield event.plain_result(prompt)

    @session_waiter(timeout=120, record_history_chains=False)
    async def waiter(controller: SessionController, wait_event: AstrMessageEvent):
        text = wait_event.message_str.strip()
        if text == "0":
            await cleanup_cvtscore_state(state)
            await wait_event.send(wait_event.plain_result("已取消操作。"))
            controller.stop()
            return

        reject_time = int(state.get("reject_time", 0) or 0)
        if reject_time > 5:
            await cleanup_cvtscore_state(state)
            await wait_event.send(wait_event.plain_result("重试次数过多，操作已取消。"))
            controller.stop()
            return

        stage = str(state.get("stage") or "need_replay")

        async def reject(msg: str):
            state["reject_time"] = reject_time + 1
            await wait_event.send(wait_event.plain_result(msg))
            controller.keep(timeout=120, reset_timeout=True)

        try:
            if stage == "need_replay":
                try:
                    found = await get_attached_file(wait_event, _REPLAY_EXTS)
                except ValueError:
                    return await reject("请发送 .osr/.mr 回放文件，或输入 0 取消。")
                if found is not None:
                    err = await load_replay_from_path(found[0], found[1], state, CACHE_DIR)
                    if err:
                        return await reject(f"回放文件处理失败: {err}\n请重新发送 .osr/.mr 文件，或输入 0 取消。")
                elif text:
                    errors = update_cvtscore_state_from_text_input(text, state)
                    if errors:
                        return await reject("参数错误:\n" + "\n".join(errors) + "\n请继续发送回放文件。")
                else:
                    return await reject("请发送回放文件（.osr/.mr）。输入 0 取消。")

            elif stage == "need_chart":
                try:
                    found = await get_attached_file(wait_event, _CHART_EXTS)
                except ValueError:
                    return await reject("请发送 .osu/.mc 谱面文件，或输入 b<bid>，输入 0 取消。")
                if found is not None:
                    err = await load_chart_from_path(found[0], found[1], state, CACHE_DIR)
                    if err:
                        return await reject(f"谱面文件处理失败: {err}\n请重新发送 .osu/.mc，或输入 b<bid>，输入 0 取消。")
                elif text:
                    parsed_bid, bid_err = parse_bid_or_url(text)
                    if bid_err is not None:
                        return await reject(f"{bid_err}\n请重新输入 b<bid>（或 mania 链接），或发送谱面文件，输入 0 取消。")
                    if parsed_bid is None:
                        errors = update_cvtscore_state_from_text_input(text, state)
                        if errors:
                            return await reject("参数错误:\n" + "\n".join(errors) + "\n请继续提供谱面。")
                        if state.get("bid") is None and state.get("osu_obj") is None:
                            return await reject("请发送 .osu/.mc 谱面文件，或输入 b<bid>。")
                    else:
                        state["bid"] = parsed_bid
                        state["bid_loaded"] = False
                        state["bid_load_error"] = None
                else:
                    return await reject("请发送 .osu/.mc 谱面文件，或输入 b<bid>。输入 0 取消。")

            elif stage == "need_ruleset":
                if not text:
                    return await reject("请输入目标 ruleset。\n" + get_ruleset_quick_help_text())
                errors = update_cvtscore_state_from_text_input(text, state)
                if errors:
                    return await reject("参数错误:\n" + "\n".join(errors) + "\n" + get_ruleset_quick_help_text())
                if not state.get("target_spec"):
                    return await reject("未解析到目标 ruleset。\n" + get_ruleset_quick_help_text())

            ready, prompt2 = await prepare_cvtscore_state(state, CACHE_DIR)
            if not ready:
                return await reject(prompt2)

            await wait_event.send(wait_event.plain_result("信息已齐全，正在转换成绩，请稍候..."))
            payload, err = await run_cvtscore_conversion(state)
            await cleanup_cvtscore_state(state)
            if err:
                await wait_event.send(wait_event.plain_result(f"转换失败: {err}"))
                controller.stop()
                return
            for m in await _build_result_messages(wait_event, payload):
                await wait_event.send(m)
            controller.stop()
        except Exception as exc:
            await cleanup_cvtscore_state(state)
            await wait_event.send(wait_event.plain_result(f"处理失败: {exc}"))
            controller.stop()

    try:
        await waiter(event)
    except TimeoutError:
        await cleanup_cvtscore_state(state)
        yield event.plain_result("操作已超时，会话结束。")
