"""Read-only environment diagnostics for Nami."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import time
from dataclasses import dataclass
from enum import Enum
from importlib import metadata
from pathlib import Path

from nami.auth import (
    AuthMode,
    cookie_candidates,
    is_browser_running,
    resolve_auth,
    validate_cookie_file,
)
from nami.config import PLATFORM_NAMES, SUPPORTED_BROWSERS, Settings, scripts_dir
from nami.models import Platform

_STALE_LOCK_SECONDS = 3600.0
_DEPENDENCIES = (
    ("gallery_dl", "gallery-dl"),
    ("yt_dlp", "yt-dlp"),
    ("rich", "rich"),
)
_CONFLICT_PACKAGES = ("urllib3_future", "niquests")
_CONFLICT_MARKERS = ("urllib3_future", "urllib3-future", "niquests")


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One structured doctor check with optional corrective guidance."""

    name: str
    status: CheckStatus
    message: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Immutable collection of local environment checks."""

    checks: tuple[CheckResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))

    @property
    def healthy(self) -> bool:
        return not any(check.status in {CheckStatus.FAIL, CheckStatus.WARN} for check in self.checks)

    def exit_code(self) -> int:
        if any(check.status is CheckStatus.FAIL for check in self.checks):
            return 1
        if any(check.status is CheckStatus.WARN for check in self.checks):
            return 3
        return 0

    def to_dict(self) -> dict[str, object]:
        return {
            "checks": [check.to_dict() for check in self.checks],
            "healthy": self.healthy,
            "exit_code": self.exit_code(),
        }


def run_doctor(settings: Settings, config_error: BaseException | str | None = None) -> DoctorReport:
    """Inspect Nami's local environment without network access or mutation."""

    checks: list[CheckResult] = []
    checks.append(_config_check(config_error))
    checks.append(_python_check())
    checks.extend(_dependency_checks())
    checks.extend(_workspace_checks(settings))
    checks.append(_browser_check(settings))
    checks.extend(_cookie_checks(settings))
    checks.extend(_profile_checks(settings))
    checks.append(_urllib3_check())
    checks.append(_archive_lock_check(settings.base_dir))
    checks.append(_path_check())
    return DoctorReport(tuple(checks))


def _config_check(config_error: BaseException | str | None) -> CheckResult:
    if config_error is None:
        return CheckResult("config", CheckStatus.PASS, "Configuration loaded successfully")
    return CheckResult(
        "config",
        CheckStatus.FAIL,
        f"Configuration could not be loaded: {config_error}",
        "Correct the configuration file or regenerate it with Nami setup",
    )


def _python_check() -> CheckResult:
    version = sys.version_info
    rendered = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) >= (3, 10):
        return CheckResult(
            "python",
            CheckStatus.PASS,
            f"Python {rendered} is supported",
        )
    return CheckResult(
        "python",
        CheckStatus.FAIL,
        f"Python {rendered} is not supported",
        "Install Python 3.10 or newer",
    )


def _dependency_checks() -> list[CheckResult]:
    checks: list[CheckResult] = []
    for module_name, distribution_name in _DEPENDENCIES:
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, AttributeError, ValueError) as exc:
            spec = None
            detail = f": {exc}"
        else:
            detail = ""
        if spec is None:
            checks.append(
                CheckResult(
                    f"dependency.{module_name}",
                    CheckStatus.FAIL,
                    f"{distribution_name} is not importable{detail}",
                    f"Install it with: python -m pip install {distribution_name}",
                )
            )
            continue
        version = _distribution_version(distribution_name)
        if version is None:
            checks.append(
                CheckResult(
                    f"dependency.{module_name}",
                    CheckStatus.WARN,
                    f"{distribution_name} is importable but its version is unknown",
                    f"Reinstall it with: python -m pip install --force-reinstall {distribution_name}",
                )
            )
        else:
            checks.append(
                CheckResult(
                    f"dependency.{module_name}",
                    CheckStatus.PASS,
                    f"{distribution_name} {version} is importable",
                )
            )
    return checks


def _workspace_checks(settings: Settings) -> list[CheckResult]:
    return [
        _directory_check("workspace.downloads", settings.base_dir),
        _directory_check("workspace.cookies", settings.cookies_dir),
        _directory_check("workspace.profiles", settings.profiles_dir),
    ]


def _directory_check(name: str, path: Path) -> CheckResult:
    try:
        exists = path.exists()
        is_directory = path.is_dir()
    except OSError as exc:
        return CheckResult(
            name,
            CheckStatus.FAIL,
            f"Workspace path cannot be inspected: {path}: {exc}",
            "Correct the path and filesystem permissions",
        )
    if not exists:
        return CheckResult(
            name,
            CheckStatus.FAIL,
            f"Workspace directory does not exist: {path}",
            "Run Nami setup to initialize the workspace",
        )
    if not is_directory:
        return CheckResult(
            name,
            CheckStatus.FAIL,
            f"Workspace path is not a directory: {path}",
            "Replace the path with a writable directory",
        )
    if not os.access(path, os.R_OK | os.W_OK):
        return CheckResult(
            name,
            CheckStatus.FAIL,
            f"Workspace directory is not readable and writable: {path}",
            "Grant the current user read and write permission",
        )
    return CheckResult(
        name,
        CheckStatus.PASS,
        f"Workspace directory is readable and writable: {path}",
    )


def _browser_check(settings: Settings) -> CheckResult:
    try:
        auth = resolve_auth(Platform.TIKTOK, settings)
    except (OSError, ValueError) as exc:
        return CheckResult(
            "browser",
            CheckStatus.FAIL,
            f"Browser authentication could not be evaluated: {exc}",
            "Correct the browser setting or provide a valid TikTok cookie file",
        )
    if auth.mode is not AuthMode.BROWSER:
        return CheckResult(
            "browser",
            CheckStatus.SKIP,
            "Browser cookie extraction is not currently required",
        )
    if settings.browser not in SUPPORTED_BROWSERS:
        return CheckResult(
            "browser",
            CheckStatus.FAIL,
            f"Configured browser is unsupported: {settings.browser}",
            f"Choose one of: {', '.join(SUPPORTED_BROWSERS)}",
        )
    if is_browser_running(settings.browser):
        return CheckResult(
            "browser",
            CheckStatus.WARN,
            f"{settings.browser} is running and may lock its cookie database",
            f"Close {settings.browser} before a TikTok download that uses browser cookies",
        )
    return CheckResult(
        "browser",
        CheckStatus.PASS,
        f"{settings.browser} is valid and is not running",
    )


def _cookie_checks(settings: Settings) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for platform in Platform:
        for candidate in cookie_candidates(platform, settings.cookies_dir):
            try:
                exists = candidate.exists()
            except OSError:
                exists = True
            if not exists:
                continue
            validation = validate_cookie_file(candidate)
            name = f"cookie.{platform.value}.{candidate.name}"
            if validation.valid:
                checks.append(
                    CheckResult(
                        name,
                        CheckStatus.PASS,
                        f"Cookie file has valid Netscape structure: {candidate}",
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        name,
                        CheckStatus.FAIL,
                        f"Cookie file is invalid: {candidate}: {validation.reason or 'unknown reason'}",
                        "Export fresh cookies in Netscape format or remove the invalid candidate",
                    )
                )
    if not checks:
        checks.append(
            CheckResult(
                "cookies",
                CheckStatus.SKIP,
                "No cookie candidate files exist",
            )
        )
    return checks


def _profile_checks(settings: Settings) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for platform in PLATFORM_NAMES:
        path = settings.profiles_dir / f"{platform}_profiles.txt"
        name = f"profile.{platform}"
        try:
            exists = path.exists()
            is_file = path.is_file()
        except OSError as exc:
            checks.append(
                CheckResult(
                    name,
                    CheckStatus.FAIL,
                    f"Profile file cannot be inspected: {path}: {exc}",
                    "Correct the profile path and permissions",
                )
            )
            continue
        if not exists:
            checks.append(
                CheckResult(
                    name,
                    CheckStatus.SKIP,
                    f"Profile file does not exist: {path}",
                )
            )
        elif not is_file or not os.access(path, os.R_OK):
            checks.append(
                CheckResult(
                    name,
                    CheckStatus.FAIL,
                    f"Profile file is not readable: {path}",
                    "Grant the current user read permission or replace the file",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name,
                    CheckStatus.PASS,
                    f"Profile file is readable: {path}",
                )
            )
    return checks


def _urllib3_check() -> CheckResult:
    try:
        spec = importlib.util.find_spec("urllib3")
    except (ImportError, AttributeError, ValueError) as exc:
        return CheckResult(
            "urllib3",
            CheckStatus.FAIL,
            f"urllib3 cannot be inspected: {exc}",
            "Reinstall urllib3 with: python -m pip install --force-reinstall urllib3",
        )
    if spec is None:
        return CheckResult(
            "urllib3",
            CheckStatus.FAIL,
            "urllib3 is not importable",
            "Install urllib3 with: python -m pip install urllib3",
        )

    origin = str(getattr(spec, "origin", "") or "")
    owners = _package_owners("urllib3")
    folded_owners = tuple(owner.casefold().replace("_", "-") for owner in owners)
    origin_folded = origin.casefold()
    installed_conflicts = tuple(
        package.replace("_", "-") for package in _CONFLICT_PACKAGES if importlib.util.find_spec(package) is not None
    )
    hijacked = any(marker in origin_folded for marker in _CONFLICT_MARKERS) or any(
        any(marker in owner for marker in _CONFLICT_MARKERS) for owner in folded_owners
    )
    if hijacked:
        return CheckResult(
            "urllib3",
            CheckStatus.FAIL,
            f"urllib3 has conflicting namespace ownership ({_owner_text(owners)})",
            "Uninstall urllib3-future/niquests, then force-reinstall urllib3",
        )
    if installed_conflicts:
        return CheckResult(
            "urllib3",
            CheckStatus.WARN,
            f"Potential urllib3 conflict package(s) are installed: {', '.join(installed_conflicts)}",
            "Remove unused conflict packages if downloader networking fails",
        )
    if not owners:
        return CheckResult(
            "urllib3",
            CheckStatus.WARN,
            "urllib3 is importable but its distribution owner is unknown",
            "Verify the environment or force-reinstall urllib3",
        )
    if "urllib3" not in folded_owners:
        return CheckResult(
            "urllib3",
            CheckStatus.WARN,
            f"urllib3 ownership is unexpected: {_owner_text(owners)}",
            "Verify the environment or force-reinstall urllib3",
        )

    version = _distribution_version("urllib3") or "unknown version"
    return CheckResult(
        "urllib3",
        CheckStatus.PASS,
        f"urllib3 {version} has expected ownership ({_owner_text(owners)})",
    )


def _archive_lock_check(base_dir: Path) -> CheckResult:
    try:
        if not base_dir.is_dir():
            return CheckResult(
                "archive_locks",
                CheckStatus.SKIP,
                "Download workspace is unavailable; archive locks were not scanned",
            )
        now = time.time()
        stale: list[Path] = []
        for path in base_dir.rglob("archive.lock"):
            try:
                if path.is_file() and now - path.stat().st_mtime >= _STALE_LOCK_SECONDS:
                    stale.append(path)
            except OSError:
                continue
    except OSError as exc:
        return CheckResult(
            "archive_locks",
            CheckStatus.WARN,
            f"Archive locks could not be scanned: {exc}",
            "Check read permission on the downloads workspace",
        )

    if stale:
        rendered = ", ".join(str(path) for path in sorted(stale))
        return CheckResult(
            "archive_locks",
            CheckStatus.WARN,
            f"Found {len(stale)} stale archive lock(s): {rendered}",
            "Verify no Nami process is using them, then remove the stale lock files",
        )
    return CheckResult(
        "archive_locks",
        CheckStatus.PASS,
        "No stale archive locks were found",
    )


def _path_check() -> CheckResult:
    if shutil.which("nami") is not None:
        return CheckResult("path", CheckStatus.PASS, "nami is available on system PATH")
    directory = scripts_dir()
    return CheckResult(
        "path",
        CheckStatus.WARN,
        "nami is not on system PATH; the 'nami' command will not work directly",
        f"Add {directory} to your system PATH, then restart your terminal; or use 'python -m nami' as a workaround",
    )


def _distribution_version(distribution_name: str) -> str | None:
    try:
        return metadata.version(distribution_name)
    except (metadata.PackageNotFoundError, ValueError, OSError):
        return None


def _package_owners(package_name: str) -> tuple[str, ...]:
    try:
        return tuple(str(owner) for owner in metadata.packages_distributions().get(package_name, ()))
    except (AttributeError, OSError, ValueError):
        return ()


def _owner_text(owners: tuple[str, ...]) -> str:
    return ", ".join(owners) if owners else "unknown owner"
