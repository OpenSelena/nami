"""Immutable, side-effect-free configuration management for Nami."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLATFORM_NAMES = ("instagram", "tiktok", "facebook", "x")
SUPPORTED_BROWSERS = ("brave", "chrome", "edge", "firefox")
DEFAULT_BROWSER = "brave"
DEFAULT_TIMEOUT_SECONDS = 1800
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 86_400
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
PROFILE_TEMPLATE = "# One profile URL per line\n"
COOKIE_TEMPLATE = "# Netscape HTTP Cookie File\n# Paste your Netscape-formatted cookies here\n"


class ConfigError(ValueError):
    """Raised when configuration cannot be loaded, validated, or saved."""


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    cookies_dir: Path
    profiles_dir: Path
    browser: str
    user_agent: str
    timeout_seconds: int
    config_file: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_dir", Path(self.base_dir).expanduser())
        object.__setattr__(self, "cookies_dir", Path(self.cookies_dir).expanduser())
        object.__setattr__(self, "profiles_dir", Path(self.profiles_dir).expanduser())
        object.__setattr__(self, "config_file", Path(self.config_file).expanduser())

        browser = str(self.browser).strip().lower()
        if browser not in SUPPORTED_BROWSERS:
            supported = ", ".join(SUPPORTED_BROWSERS)
            raise ConfigError(f"browser must be one of: {supported}")
        object.__setattr__(self, "browser", browser)

        if not isinstance(self.timeout_seconds, int) or isinstance(self.timeout_seconds, bool):
            raise ConfigError("timeout_seconds must be an integer")
        if not MIN_TIMEOUT_SECONDS <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ConfigError(f"timeout_seconds must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS}")
        if not isinstance(self.user_agent, str) or not self.user_agent.strip():
            raise ConfigError("user_agent must be a non-empty string")
        object.__setattr__(self, "user_agent", self.user_agent.strip())


class ConfigRepository:
    """Load and atomically save Settings without import-time environment state."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        home: Path | str | None = None,
    ) -> None:
        self.home = Path.home() if home is None else Path(home)
        self.path = self.home / ".nami" / "nami_config.json" if path is None else Path(path).expanduser()
        self.environ = os.environ if environ is None else environ

    def load(self) -> Settings:
        defaults = settings_for_root(self.home, config_file=self.path)
        data = self._read_file()
        env = self.environ

        env_base = self._environment_value("NAMI_BASE_DIR")
        file_base = self._file_value(data, "base_dir")
        base = self._path_value(env_base if env_base is not None else file_base, defaults.base_dir, "base_dir")

        env_cookies = self._environment_value("NAMI_COOKIES_DIR")
        env_profiles = self._environment_value("NAMI_PROFILES_DIR")
        if env_base is not None:
            cookie_source: object = env_cookies if env_cookies is not None else base.parent / "cookies"
            profile_source: object = env_profiles if env_profiles is not None else base.parent / "profiles"
        else:
            cookie_source = env_cookies
            if cookie_source is None:
                cookie_source = self._file_value(data, "cookies_dir")
            if cookie_source is None and file_base is not None:
                cookie_source = base.parent / "cookies"

            profile_source = env_profiles
            if profile_source is None:
                profile_source = self._file_value(data, "profiles_dir")
            if profile_source is None and file_base is not None:
                profile_source = base.parent / "profiles"

        cookies = self._path_value(cookie_source, defaults.cookies_dir, "cookies_dir")
        profiles = self._path_value(profile_source, defaults.profiles_dir, "profiles_dir")

        browser = self._setting_value(env, "NAMI_BROWSER", data, "browser", defaults.browser)
        user_agent = self._setting_value(env, "NAMI_USER_AGENT", data, "user_agent", defaults.user_agent)
        timeout_raw = self._timeout_value(data, defaults.timeout_seconds)
        timeout = self._parse_timeout(timeout_raw)

        try:
            return Settings(
                base_dir=base,
                cookies_dir=cookies,
                profiles_dir=profiles,
                browser=str(browser),
                user_agent=str(user_agent),
                timeout_seconds=timeout,
                config_file=self.path,
            )
        except ConfigError:
            raise
        except (TypeError, ValueError, OSError) as exc:
            raise ConfigError(f"invalid configuration: {exc}") from exc

    def save(self, settings: Settings) -> None:
        """Atomically persist settings using a same-directory temporary file."""
        parent = self.path.parent
        temp_path: Path | None = None
        payload = {
            "base_dir": str(settings.base_dir),
            "cookies_dir": str(settings.cookies_dir),
            "profiles_dir": str(settings.profiles_dir),
            "browser": settings.browser,
            "user_agent": settings.user_agent,
            "timeout_seconds": settings.timeout_seconds,
        }

        try:
            parent.mkdir(parents=True, exist_ok=True)
            _chmod(parent, 0o700)
            fd, raw_temp_path = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=str(parent))
            temp_path = Path(raw_temp_path)
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            temp_path = None
            _chmod(self.path, 0o600)
        except (OSError, TypeError, ValueError) as exc:
            raise ConfigError(f"could not save config {self.path}: {exc}") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

    def _read_file(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"malformed JSON in config {self.path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        except OSError as exc:
            raise ConfigError(f"could not read config {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"config {self.path} must contain a JSON object")
        return data

    def _environment_value(self, key: str) -> str | None:
        return self.environ.get(key)

    @staticmethod
    def _file_value(data: Mapping[str, Any], key: str) -> Any:
        return data.get(key)

    @staticmethod
    def _path_value(value: object, default: Path, name: str) -> Path:
        if value is None:
            return default
        if not isinstance(value, (str, os.PathLike)):
            raise ConfigError(f"{name} must be a path string")
        raw = os.fspath(value)
        if not raw.strip():
            raise ConfigError(f"{name} must not be empty")
        return Path(raw).expanduser()

    @staticmethod
    def _setting_value(
        env: Mapping[str, str],
        env_key: str,
        data: Mapping[str, Any],
        file_key: str,
        default: object,
    ) -> object:
        if env_key in env:
            return env[env_key]
        if file_key in data:
            return data[file_key]
        return default

    def _timeout_value(self, data: Mapping[str, Any], default: int) -> object:
        if "NAMI_TIMEOUT_SECONDS" in self.environ:
            return self.environ["NAMI_TIMEOUT_SECONDS"]
        if "NAMI_TIMEOUT" in self.environ:
            return self.environ["NAMI_TIMEOUT"]
        if "timeout_seconds" in data:
            return data["timeout_seconds"]
        if "timeout" in data:
            return data["timeout"]
        return default

    @staticmethod
    def _parse_timeout(value: object) -> int:
        if isinstance(value, bool):
            raise ConfigError("timeout_seconds must be an integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError("timeout_seconds must be an integer") from exc
        if isinstance(value, float) and not value.is_integer():
            raise ConfigError("timeout_seconds must be an integer")
        if isinstance(value, str) and str(parsed) != value.strip():
            raise ConfigError("timeout_seconds must be an integer")
        return parsed


def settings_for_root(
    root: Path | str,
    *,
    config_file: Path | str | None = None,
    browser: str = DEFAULT_BROWSER,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Settings:
    """Build settings for ``root/Nami`` without touching the filesystem."""
    root_path = Path(root).expanduser()
    nami_root = root_path / "Nami"
    chosen_config = root_path / ".nami" / "nami_config.json" if config_file is None else Path(config_file).expanduser()
    return Settings(
        base_dir=nami_root / "downloads",
        cookies_dir=nami_root / "cookies",
        profiles_dir=nami_root / "profiles",
        browser=browser,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
        config_file=chosen_config,
    )


def initialize_workspace(settings: Settings, *, create_cookie_templates: bool = False) -> None:
    """Create workspace directories and non-destructive template files."""
    try:
        settings.base_dir.mkdir(parents=True, exist_ok=True)
        settings.cookies_dir.mkdir(parents=True, exist_ok=True)
        settings.profiles_dir.mkdir(parents=True, exist_ok=True)
        settings.config_file.parent.mkdir(parents=True, exist_ok=True)
        _chmod(settings.cookies_dir, 0o700)
        _chmod(settings.config_file.parent, 0o700)

        for platform in PLATFORM_NAMES:
            _create_template(settings.profiles_dir / f"{platform}_profiles.txt", PROFILE_TEMPLATE)
        if create_cookie_templates:
            for platform in PLATFORM_NAMES:
                _create_template(settings.cookies_dir / f"{platform}_cookies.txt", COOKIE_TEMPLATE)
    except OSError as exc:
        raise ConfigError(f"could not initialize Nami workspace: {exc}") from exc


def _create_template(path: Path, content: str) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    _chmod(path, 0o600)


def _chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass
