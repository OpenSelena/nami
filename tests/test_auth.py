import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nami.auth import (
    AuthMode,
    AuthSpec,
    auth_cli_args,
    is_browser_running,
    resolve_auth,
    validate_cookie_file,
)
from nami.config import initialize_workspace, settings_for_root
from nami.models import Platform

_VALID_ROW = ".instagram.com\tTRUE\t/\tFALSE\t1700000000\tsessionid\tsecret-value\n"


def test_cookie_validation_rejects_missing_header_only_and_malformed(
    tmp_path: Path,
) -> None:
    missing = validate_cookie_file(tmp_path / "missing.txt")
    assert not missing.valid

    header = tmp_path / "header.txt"
    header.write_text("# Netscape HTTP Cookie File\n# placeholder\n", encoding="utf-8")
    validation = validate_cookie_file(header)
    assert not validation
    assert validation.valid_rows == 0
    assert "secret-value" not in (validation.reason or "")

    malformed = tmp_path / "malformed.txt"
    malformed.write_text("domain spaces are not tabs secret-value\n", encoding="utf-8")
    assert not validate_cookie_file(malformed).valid


def test_cookie_validation_accepts_at_least_seven_tab_fields(tmp_path: Path) -> None:
    path = tmp_path / "cookies.txt"
    path.write_text("# Netscape HTTP Cookie File\n" + _VALID_ROW, encoding="utf-8")
    validation = validate_cookie_file(path)
    assert validation.valid
    assert validation.valid_rows == 1
    assert "secret-value" not in repr(validation)

    http_only = tmp_path / "http-only.txt"
    http_only.write_text(f"#HttpOnly_{_VALID_ROW}", encoding="utf-8")
    assert validate_cookie_file(http_only).valid


def test_resolve_auth_skips_placeholder_and_uses_first_valid_candidate(
    tmp_path: Path,
) -> None:
    settings = settings_for_root(tmp_path)
    initialize_workspace(settings, create_cookie_templates=True)
    valid = settings.cookies_dir / "instagram.com_cookies.txt"
    valid.write_text(_VALID_ROW, encoding="utf-8")

    spec = resolve_auth(Platform.INSTAGRAM, settings)
    assert spec == AuthSpec(AuthMode.COOKIE_FILE, cookie_file=valid)
    assert auth_cli_args(spec) == ["--cookies", str(valid)]


def test_x_twitter_cookie_aliases_are_supported(tmp_path: Path) -> None:
    settings = settings_for_root(tmp_path)
    initialize_workspace(settings)
    twitter = settings.cookies_dir / "twitter_cookies.txt"
    twitter.write_text(_VALID_ROW, encoding="utf-8")
    assert resolve_auth("twitter", settings).cookie_file == twitter


def test_browser_fallback_is_tiktok_only(tmp_path: Path) -> None:
    settings = settings_for_root(tmp_path, browser="firefox")
    initialize_workspace(settings, create_cookie_templates=True)
    tiktok = resolve_auth(Platform.TIKTOK, settings)
    instagram = resolve_auth(Platform.INSTAGRAM, settings)
    assert tiktok == AuthSpec(AuthMode.BROWSER, browser="firefox")
    assert auth_cli_args(tiktok) == ["--cookies-from-browser", "firefox"]
    assert instagram == AuthSpec(AuthMode.NONE)
    assert auth_cli_args(instagram) == []


def test_invalid_auth_specs_do_not_generate_cli_args() -> None:
    with pytest.raises(ValueError):
        auth_cli_args(AuthSpec(AuthMode.COOKIE_FILE))
    with pytest.raises(ValueError):
        auth_cli_args(AuthSpec(AuthMode.BROWSER, browser="safari"))


def test_browser_process_detection_uses_configured_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        assert kwargs["timeout"] == 5
        return SimpleNamespace(stdout="firefox\n", returncode=0)

    monkeypatch.setattr("nami.auth.sys.platform", "linux")
    monkeypatch.setattr("nami.auth.subprocess.run", fake_run)
    assert is_browser_running("firefox")
    assert not is_browser_running("brave")
    assert calls == [["ps", "-A", "-o", "comm="], ["ps", "-A", "-o", "comm="]]


def test_browser_process_detection_is_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("ps", 5)

    monkeypatch.setattr("nami.auth.subprocess.run", fail)
    assert not is_browser_running("chrome")
    assert not is_browser_running("unsupported")
