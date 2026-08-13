"""Authentication and cookie handling for Nami."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SUPPORTED_BROWSERS = {"brave", "chrome", "edge", "firefox"}


def validate_browser(browser: str) -> bool:
    return browser.strip().lower() in SUPPORTED_BROWSERS


@dataclass
class AuthConfig:
    mode: Literal["netscape", "browser", "none"]
    path: Path | None = None
    browser: str | None = None
    username: str | None = None

    def to_cli_args(self) -> list[str]:
        if self.mode == "netscape" and self.path is not None:
            return ["--cookies", str(self.path)]
        elif self.mode == "browser" and self.browser:
            return ["--cookies-from-browser", self.browser]
        return []


def is_brave_running() -> bool:
    """Return True if a Brave process appears to be running."""
    try:
        if sys.platform == "win32":
            res = subprocess.run(
                ["tasklist", "/fi", "imagename eq brave.exe"],
                capture_output=True, text=True, timeout=5
            )
            return "brave.exe" in res.stdout.lower()
        else:
            res = subprocess.run(
                ["pgrep", "-f", "Brave"],
                capture_output=True, text=True, timeout=5
            )
            return bool(res.stdout.strip())
    except Exception:
        return False


def validate_cookie(file_path: Path | str) -> bool:
    path = Path(file_path)
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "Netscape HTTP Cookie File" in content:
            return True
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                if len(line.split("\t")) >= 7:
                    return True
                break
    except Exception:
        pass
    return False


def resolve_authentication(
    platform: str,
    cookies_dir: Path | None,
    browser: str,
    target_username: str | None = None,
) -> AuthConfig:
    browser_clean = browser.strip().lower() if validate_browser(browser) else "brave"

    if cookies_dir is not None:
        cookie_file = cookies_dir / f"{platform}.com_cookies.txt"
        if cookie_file.exists() and validate_cookie(cookie_file):
            return AuthConfig(mode="netscape", path=cookie_file)

    if platform == "tiktok":
        return AuthConfig(mode="browser", browser=browser_clean)

    return AuthConfig(mode="none")
