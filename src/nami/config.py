"""Configuration management for Nami."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".nami"
CONFIG_FILE = CONFIG_DIR / "nami_config.json"
PLATFORMS = ("instagram", "tiktok", "facebook", "x")
PROFILE_FILES = tuple(f"{p}_profiles.txt" for p in PLATFORMS)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
UA = os.environ.get("NAMI_USER_AGENT", DEFAULT_UA)
MAX_RETRIES = 2
DEFAULT_TIMEOUT = int(os.environ.get("NAMI_TIMEOUT", "1800"))

PHOTO_FILTER = (
    "extension in ('jpg','jpeg','png','gif','webp','bmp','jfif',"
    "'heic','avif','tiff','svg')"
)
VIDEO_FILTER = (
    "extension in ('mp4','webm','mkv','mov','avi','m4v','flv','wmv',"
    "'3gp','mpeg','mpg','ts','f4v','mts','m2ts')"
)
MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".jfif", ".heic",
    ".avif", ".tiff", ".svg", ".mp4", ".webm", ".mkv", ".mov", ".avi",
    ".m4v", ".flv", ".wmv", ".3gp", ".mpeg", ".mpg", ".ts", ".f4v",
    ".mts", ".m2ts",
}


class Config:
    def __init__(self) -> None:
        self.base_dir: Path | None = None
        self.cookies_dir: Path | None = None
        self.profiles_dir: Path | None = None
        self.browser: str = "brave"
        self.debug_log: Path | None = None

    def is_configured(self) -> bool:
        if self.base_dir is None or self.cookies_dir is None or self.profiles_dir is None:
            return False
        try:
            return self.base_dir.is_dir() and self.cookies_dir.is_dir() and self.profiles_dir.is_dir()
        except OSError:
            return False

    def load(self) -> None:
        self.base_dir = None
        self.cookies_dir = None
        self.profiles_dir = None
        self.browser = "brave"
        self.debug_log = None

        if not CONFIG_FILE.exists():
            if os.environ.get("NAMI_BASE_DIR") and os.environ.get("NAMI_COOKIES_DIR"):
                try:
                    self.base_dir = Path(os.environ["NAMI_BASE_DIR"]).expanduser().resolve()
                    self.cookies_dir = Path(os.environ["NAMI_COOKIES_DIR"]).expanduser().resolve()
                    env_prof = os.environ.get("NAMI_PROFILES_DIR")
                    if env_prof:
                        self.profiles_dir = Path(env_prof).expanduser().resolve()
                    else:
                        self.profiles_dir = self.base_dir.parent / "profiles"
                    self.browser = os.environ.get("NAMI_BROWSER", "brave").strip() or "brave"
                    self.debug_log = self.base_dir / "nami_debug.log"
                except Exception:
                    self.base_dir = self.cookies_dir = self.profiles_dir = None
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
        except (json.JSONDecodeError, OSError):
            return

        base = data.get("base_dir") or os.environ.get("NAMI_BASE_DIR")
        cookies = data.get("cookies_dir") or os.environ.get("NAMI_COOKIES_DIR")
        profiles = data.get("profiles_dir") or os.environ.get("NAMI_PROFILES_DIR")
        browser = data.get("browser") or os.environ.get("NAMI_BROWSER") or "brave"

        if base:
            try:
                self.base_dir = Path(str(base)).expanduser().resolve()
            except Exception:
                self.base_dir = None
        if cookies:
            try:
                self.cookies_dir = Path(str(cookies)).expanduser().resolve()
            except Exception:
                self.cookies_dir = None
        if profiles:
            try:
                self.profiles_dir = Path(str(profiles)).expanduser().resolve()
            except Exception:
                self.profiles_dir = None
        elif self.base_dir is not None:
            self.profiles_dir = self.base_dir.parent / "profiles"

        self.browser = str(browser).strip() or "brave"
        if self.base_dir is not None:
            self.debug_log = self.base_dir / "nami_debug.log"

    def save(self) -> bool:
        if self.base_dir is None or self.cookies_dir is None or self.profiles_dir is None:
            return False
        data = {
            "base_dir": str(self.base_dir),
            "cookies_dir": str(self.cookies_dir),
            "profiles_dir": str(self.profiles_dir),
            "browser": self.browser,
        }
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self._set_secure_permissions(CONFIG_DIR)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._set_secure_permissions(CONFIG_FILE)
            return True
        except OSError:
            return False

    def ensure_dirs(self) -> bool:
        if self.base_dir is None or self.cookies_dir is None or self.profiles_dir is None:
            return False
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self.cookies_dir.mkdir(parents=True, exist_ok=True)
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            self._set_secure_permissions(self.cookies_dir)

            for name in PROFILE_FILES:
                path = self.profiles_dir / name
                if not path.exists():
                    path.write_text("# One profile URL per line\n", encoding="utf-8")
            return True
        except OSError:
            return False

    def _set_secure_permissions(self, path: Path) -> None:
        """Apply 0600 (file) or 0700 (dir) permissions on Unix platforms for security."""
        if sys.platform != "win32" and path.exists():
            try:
                mode = 0o700 if path.is_dir() else 0o600
                path.chmod(mode)
            except Exception:
                pass


config = Config()
