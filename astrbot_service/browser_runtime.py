from __future__ import annotations

import atexit
import functools
import json
import logging
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from .errors import ManiaMapAnalyserError

logger = logging.getLogger(__name__)


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()


class StaticFileServer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.port: int | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler = functools.partial(_QuietStaticHandler, directory=str(self.root))
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ma-static-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return

        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self.port = None

        self._thread.join(timeout=2)
        self._thread = None


@dataclass(frozen=True)
class RenderRequest:
    output_path: Path
    payload: dict[str, Any]
    capture_target: str


DEFAULT_IDLE_TIMEOUT_SECONDS: int = 600


class ChromiumRenderRuntime:
    def __init__(
        self,
        static_root: Path,
        idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self.static_root = static_root
        self.idle_timeout_seconds = max(10, idle_timeout_seconds)
        self._jobs: Queue[tuple[RenderRequest, Future[Path]] | None] = Queue()
        self._ready = threading.Event()
        self._closed = False
        self._static_server: StaticFileServer | None = None
        self._browser = None
        self._context = None
        self._playwright = None
        self._bridge_url: str | None = None
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="ma-browser-worker",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.close)

    def render(self, request: RenderRequest) -> Path:
        self._ready.wait()
        if self._closed:
            raise ManiaMapAnalyserError("Chromium 渲染线程已关闭")

        future: Future[Path] = Future()
        self._jobs.put((request, future))
        return future.result()

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        self._jobs.put(None)
        self._thread.join(timeout=5)

    def _ensure_runtime_ready(self) -> None:
        if self._static_server is None:
            self._static_server = StaticFileServer(self.static_root)
            self._static_server.start()
            self._bridge_url = (
                f"http://127.0.0.1:{self._static_server.port}"
                "/bridge/render_bridge.html"
            )
        if self._browser is None:
            self._launch_browser()

    def _worker_loop(self) -> None:
        self._ready.set()

        while not self._closed:
            try:
                job = self._jobs.get(timeout=self.idle_timeout_seconds)
            except Empty:
                if self._browser is not None:
                    logger.info(
                        "Chromium 渲染进程闲置超时 (%ds)，已自动关闭以释放内存",
                        self.idle_timeout_seconds,
                    )
                    self._term_browser()
                continue

            if job is None:
                break
            request, future = job

            try:
                self._ensure_runtime_ready()
                result = self._render_page(request)
            except Exception as exc:
                normalized = (
                    exc
                    if isinstance(exc, ManiaMapAnalyserError)
                    else self._normalize_startup_error(exc)
                    if self._browser is None
                    else exc
                )
                future.set_exception(normalized)
                if self._is_browser_crash(exc):
                    self._term_browser()
            else:
                future.set_result(result)

        self._shutdown_worker()

    def _render_page(self, request: RenderRequest) -> Path:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        page = self._context.new_page()
        page.set_default_timeout(120000)
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda message: console_errors.append(f"{message.type}: {message.text}")
            if message.type in {"error", "warning"}
            else None,
        )

        try:
            payload_json = json.dumps(request.payload, ensure_ascii=False)
            page.add_init_script(script=f"window.__MA_RENDER_PAYLOAD = {payload_json};")
            page.goto(self._bridge_url, wait_until="load")
            page.wait_for_load_state("networkidle")
            page.wait_for_function("window.__MA_RENDER_DONE === true")
            render_state = page.evaluate(
                "() => ({"
                "error: window.__MA_RENDER_ERROR || null,"
                "errorStack: window.__MA_RENDER_ERROR_STACK || '',"
                "statusText: window.__MA_RENDER_STATUS_TEXT || '',"
                "statusKind: window.__MA_RENDER_STATUS_KIND || ''"
                "})"
            )
            if render_state["error"]:
                error_message = str(render_state["error"])
                error_stack = self._trim_stack(render_state.get("errorStack"))
                if error_stack:
                    error_message = f"{error_message} | {error_stack}"
                raise ManiaMapAnalyserError(error_message)

            selector = "#body-graph-wrap" if request.capture_target == "graph_only" else "#capture-surface"
            page.locator(selector).screenshot(
                path=str(request.output_path),
                animations="disabled",
            )
        except Exception as exc:
            diagnostics = self._build_page_diagnostics(page_errors, console_errors)
            raise self._normalize_runtime_error(exc, diagnostics) from exc
        finally:
            page.close()

        return request.output_path

    def _shutdown_worker(self) -> None:
        self._term_browser()

        if self._static_server is not None:
            self._static_server.stop()
            self._static_server = None

    def _launch_browser(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--font-render-hinting=medium",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 900, "height": 1400},
            device_scale_factor=2,
            color_scheme="dark",
        )

    def _term_browser(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    @staticmethod
    def _is_browser_crash(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(indicator in message for indicator in [
            "target crashed",
            "browser has been closed",
            "target page, context or browser has been closed",
        ])

    def _normalize_startup_error(self, exc: Exception) -> ManiaMapAnalyserError:
        message = str(exc)
        lowered = message.lower()
        if "no module named 'playwright'" in lowered:
            return ManiaMapAnalyserError(
                "Playwright 运行时未就绪，插件自动安装依赖失败：" + message
            )
        if "executable doesn't exist" in lowered or "browsertype.launch" in lowered:
            return ManiaMapAnalyserError(
                "Chromium 内核未就绪，插件自动安装浏览器失败：" + message
            )
        return ManiaMapAnalyserError(f"启动 Chromium 失败：{message}")

    def _normalize_runtime_error(
        self,
        exc: Exception,
        diagnostics: str = "",
    ) -> ManiaMapAnalyserError:
        if isinstance(exc, ManiaMapAnalyserError):
            if diagnostics:
                return ManiaMapAnalyserError(f"{exc} | {diagnostics}")
            return exc

        message = f"Playwright 渲染失败：{exc}"
        if diagnostics:
            message = f"{message} | {diagnostics}"
        return ManiaMapAnalyserError(message)

    @staticmethod
    def _trim_stack(stack_text: Any) -> str:
        if not isinstance(stack_text, str):
            return ""

        lines = [line.strip() for line in stack_text.splitlines() if line.strip()]
        if not lines:
            return ""

        return " <- ".join(lines[:3])

    @staticmethod
    def _build_page_diagnostics(page_errors: list[str], console_errors: list[str]) -> str:
        chunks: list[str] = []
        if page_errors:
            chunks.append(f"pageerror={page_errors[0]}")
        if console_errors:
            chunks.append(f"console={console_errors[0]}")
        return "; ".join(chunks)
