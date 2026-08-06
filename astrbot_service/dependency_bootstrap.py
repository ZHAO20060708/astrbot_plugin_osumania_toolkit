from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_REQUIRED_MODULES = {
    "playwright": "playwright",
    "PIL": "Pillow",
    "aiohttp": "aiohttp",
}


def bootstrap_plugin_runtime(plugin_root: Path, plugin_data_root: Path) -> None:
    runtime_root = plugin_data_root / "runtime"
    vendor_dir = runtime_root / "site-packages"
    browser_dir = runtime_root / "ms-playwright"
    state_file = runtime_root / "dependency_state.json"
    requirements_path = plugin_root / "requirements.txt"

    runtime_root.mkdir(parents=True, exist_ok=True)
    vendor_dir.mkdir(parents=True, exist_ok=True)

    _prepend_sys_path(vendor_dir)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)

    expected_state = _build_expected_state(requirements_path)
    saved_state = _load_state(state_file)
    missing_modules = _find_missing_modules()
    # AstrBot installs requirements.txt before importing the plugin. A private
    # target directory is only a fallback for non-standard installations.
    packages_ready = not missing_modules
    browser_ready = _has_playwright_browser(browser_dir)
    missing_browser_libraries = (
        _find_missing_browser_libraries(browser_dir) if browser_ready else []
    )

    if packages_ready and browser_ready and not missing_browser_libraries:
        return

    install_env = _build_install_env(vendor_dir, browser_dir)

    if not packages_ready:
        logger.info("Installing plugin dependencies into %s", vendor_dir)
        _run_command(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-warn-script-location",
                "--upgrade",
                "--target",
                str(vendor_dir),
                "-r",
                str(requirements_path),
            ],
            env=install_env,
            timeout=900,
            error_prefix="安装插件 Python 依赖失败",
        )
        importlib.invalidate_caches()
        _prepend_sys_path(vendor_dir)

        missing_modules = _find_missing_modules()
        if missing_modules:
            raise RuntimeError(
                "插件依赖安装后仍无法导入: " + ", ".join(sorted(missing_modules))
            )

        # 依赖版本变化时，Playwright 所需的 Chromium revision 也可能变化。
        # 重新检测，避免把旧 revision 的可执行文件误判为当前版本可用。
        browser_ready = _has_playwright_browser(browser_dir)

        saved_state = dict(expected_state)
        saved_state["browser_installed"] = False
        _save_state(state_file, saved_state)

    if not browser_ready:
        logger.info("Installing Playwright Chromium into %s", browser_dir)
        _run_command(
            [
                sys.executable,
                "-m",
                "playwright",
                "install",
                "chromium",
            ],
            env=install_env,
            timeout=1800,
            error_prefix="安装 Playwright Chromium 失败",
        )
        if not _has_playwright_browser(browser_dir):
            raise RuntimeError(
                "Playwright Chromium 安装命令已结束，但未找到当前版本所需的浏览器内核"
            )
        saved_state = dict(expected_state)
        saved_state["browser_installed"] = True
        _save_state(state_file, saved_state)

    missing_browser_libraries = _find_missing_browser_libraries(browser_dir)
    if missing_browser_libraries:
        logger.info(
            "Installing Playwright Chromium system dependencies: %s",
            ", ".join(missing_browser_libraries),
        )
        _run_command(
            [
                sys.executable,
                "-m",
                "playwright",
                "install-deps",
                "chromium",
            ],
            env=install_env,
            timeout=1800,
            error_prefix="安装 Playwright Chromium 系统依赖失败",
        )
        missing_browser_libraries = _find_missing_browser_libraries(browser_dir)
        if missing_browser_libraries:
            raise RuntimeError(
                "Playwright Chromium 系统依赖安装后仍有缺失: "
                + ", ".join(missing_browser_libraries)
            )


def _prepend_sys_path(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _build_expected_state(requirements_path: Path) -> dict[str, object]:
    digest = hashlib.sha256(requirements_path.read_bytes()).hexdigest()
    return {
        "requirements_sha256": digest,
        "python_executable": sys.executable,
        "python_version": list(sys.version_info[:3]),
    }


def _load_state(state_file: Path) -> dict[str, object]:
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(state_file: Path, state: dict[str, object]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _find_missing_modules() -> list[str]:
    missing: list[str] = []
    for module_name in _REQUIRED_MODULES:
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    return missing


def _has_playwright_browser(browser_dir: Path) -> bool:
    return _find_playwright_browser_executable(browser_dir) is not None


def _find_playwright_browser_executable(browser_dir: Path) -> Path | None:
    if not browser_dir.is_dir():
        return None

    try:
        playwright_spec = importlib.util.find_spec("playwright")
        if playwright_spec is None or playwright_spec.origin is None:
            return None
        browsers_file = (
            Path(playwright_spec.origin).parent
            / "driver"
            / "package"
            / "browsers.json"
        )
        browsers = json.loads(browsers_file.read_text(encoding="utf-8"))["browsers"]
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None

    executable_names = {
        "chrome",
        "chrome.exe",
        "chromium",
        "chromium.exe",
        "headless_shell",
        "headless_shell.exe",
        "headless-shell",
        "headless-shell.exe",
        "chrome-headless-shell",
        "chrome-headless-shell.exe",
    }

    chromium_entries = [
        browser
        for browser in browsers
        if browser.get("name") in {"chromium", "chromium-headless-shell"}
    ]
    headless_shell_entries = [
        browser
        for browser in chromium_entries
        if browser.get("name") == "chromium-headless-shell"
    ]
    required_entries = headless_shell_entries or chromium_entries

    candidates: list[Path] = []
    for browser in required_entries:
        name = browser.get("name")
        revision = browser.get("revision")
        if not revision:
            continue
        directory_name = str(name).replace("-", "_")
        candidates.append(browser_dir / f"{directory_name}-{revision}")

    for candidate in candidates:
        if not candidate.is_dir():
            continue
        for path in candidate.rglob("*"):
            if path.is_file() and path.name.lower() in executable_names:
                return path
    return None


def _find_missing_browser_libraries(browser_dir: Path) -> list[str]:
    if not sys.platform.startswith("linux"):
        return []

    executable = _find_playwright_browser_executable(browser_dir)
    if executable is None:
        return []

    try:
        completed = subprocess.run(
            ["ldd", str(executable)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Unable to inspect Chromium shared libraries: %s", exc)
        return ["共享库检测工具不可用"]

    output = "\n".join(
        chunk for chunk in (completed.stdout, completed.stderr) if chunk
    )
    missing = []
    for line in output.splitlines():
        if "=> not found" not in line:
            continue
        library_name = line.split("=>", 1)[0].strip()
        if library_name:
            missing.append(library_name)
    return sorted(set(missing))


def _build_install_env(vendor_dir: Path, browser_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{vendor_dir}{os.pathsep}{python_path}" if python_path else str(vendor_dir)
    )
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    return env


def _run_command(
    command: list[str],
    env: dict[str, str],
    timeout: int,
    error_prefix: str,
) -> None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        details = _tail_command_output(exc.stdout, exc.stderr)
        raise RuntimeError(f"{error_prefix}: {details}") from exc
    except Exception as exc:
        raise RuntimeError(f"{error_prefix}: {exc}") from exc

    if completed.stderr:
        logger.debug("%s stderr: %s", command[0], completed.stderr.strip())


def _tail_command_output(stdout: str | None, stderr: str | None) -> str:
    chunks = []
    if stderr:
        chunks.append(stderr.strip())
    if stdout:
        chunks.append(stdout.strip())

    merged = "\n".join(chunk for chunk in chunks if chunk).strip()
    if not merged:
        return "无输出"

    lines = merged.splitlines()
    return " | ".join(lines[-8:])
