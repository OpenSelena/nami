"""Authentication source selection without exposing cookie contents."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import SUPPORTED_BROWSERS, Settings
from .models import Platform


class AuthMode(str, Enum):
    NONE = "none"
    COOKIE_FILE = "cookie_file"
    BROWSER = "browser"


@dataclass(frozen=True)
class AuthSpec:
    mode: AuthMode
    cookie_file: Path | None = None
    browser: str | None = None


@dataclass(frozen=True)
class CookieValidation:
    path: Path
    valid: bool
    valid_rows: int = 0
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.valid


_BROWSER_PROCESSES = {
    "brave": ("brave.exe", "brave", "Brave Browser", "Brave-Browser"),
    "chrome": ("chrome.exe", "chrome", "Google Chrome"),
    "edge": ("msedge.exe", "msedge", "Microsoft Edge"),
    "firefox": ("firefox.exe", "firefox", "Firefox"),
}


def validate_cookie_file(file_path: Path | str) -> CookieValidation:
    """Validate structure only; no cookie value is returned or logged."""
    path = Path(file_path)
    try:
        is_file = path.is_file()
    except OSError:
        is_file = False
    if not is_file:
        return CookieValidation(path, False, reason="cookie file does not exist")

    valid_rows = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.rstrip("\r\n")
                if not stripped.strip():
                    continue
                if stripped.startswith("#HttpOnly_"):
                    stripped = stripped.removeprefix("#HttpOnly_")
                elif stripped.lstrip().startswith("#"):
                    continue
                fields = stripped.split("\t")
                if len(fields) >= 7 and fields[0].strip() and fields[5].strip():
                    valid_rows += 1
    except OSError:
        return CookieValidation(path, False, reason="cookie file could not be read")

    if valid_rows == 0:
        return CookieValidation(
            path,
            False,
            reason="cookie file contains no valid Netscape cookie rows",
        )
    return CookieValidation(path, True, valid_rows=valid_rows)


def cookie_candidates(platform: Platform | str, cookies_dir: Path | str) -> tuple[Path, ...]:
    selected = _coerce_platform(platform)
    root = Path(cookies_dir)
    names = [
        f"{selected.value}_cookies.txt",
        f"{selected.value}.com_cookies.txt",
    ]
    if selected is Platform.X:
        names.extend(["twitter_cookies.txt", "twitter.com_cookies.txt"])
    return tuple(root / name for name in names)


def resolve_auth(platform: Platform | str, settings: Settings) -> AuthSpec:
    """Select the first valid explicit cookie file, then safe platform fallback."""
    selected = _coerce_platform(platform)
    for candidate in cookie_candidates(selected, settings.cookies_dir):
        if validate_cookie_file(candidate).valid:
            return AuthSpec(AuthMode.COOKIE_FILE, cookie_file=candidate)
    if selected is Platform.TIKTOK:
        return AuthSpec(AuthMode.BROWSER, browser=settings.browser)
    return AuthSpec(AuthMode.NONE)


def auth_cli_args(spec: AuthSpec) -> list[str]:
    if spec.mode is AuthMode.COOKIE_FILE:
        if spec.cookie_file is None:
            raise ValueError("cookie_file mode requires a cookie file")
        return ["--cookies", str(spec.cookie_file)]
    if spec.mode is AuthMode.BROWSER:
        if spec.browser not in SUPPORTED_BROWSERS:
            raise ValueError("browser mode requires a supported browser")
        return ["--cookies-from-browser", spec.browser]
    return []


def is_browser_running(browser: str) -> bool:
    """Best-effort cross-platform process detection for the configured browser."""
    normalized = browser.strip().lower()
    if normalized not in SUPPORTED_BROWSERS:
        return False
    names = _BROWSER_PROCESSES[normalized]
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        else:
            result = subprocess.run(
                ["ps", "-A", "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        return False
    output = result.stdout.casefold()
    return any(name.casefold() in output for name in names)


def _coerce_platform(value: Platform | str) -> Platform:
    if isinstance(value, Platform):
        return value
    normalized = str(value).strip().lower()
    if normalized == "twitter":
        normalized = "x"
    try:
        return Platform(normalized)
    except ValueError as exc:
        raise ValueError(f"unsupported platform: {value}") from exc
