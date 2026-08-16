from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nami import doctor
from nami.config import PLATFORM_NAMES, Settings, settings_for_root
from nami.doctor import CheckStatus, run_doctor


def prepare_workspace(tmp_path: Path) -> Settings:
    settings = settings_for_root(tmp_path)
    settings.base_dir.mkdir(parents=True)
    settings.cookies_dir.mkdir(parents=True)
    settings.profiles_dir.mkdir(parents=True)
    for platform in PLATFORM_NAMES:
        (settings.profiles_dir / f"{platform}_profiles.txt").write_text("# profiles\n", encoding="utf-8")
    return settings


def patch_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    missing: frozenset[str] = frozenset(),
    conflicts: frozenset[str] = frozenset(),
) -> None:
    available = {"gallery_dl", "yt_dlp", "rich", "urllib3"}

    def find_spec(name: str) -> object | None:
        if name in missing:
            return None
        if name in conflicts:
            return SimpleNamespace(origin=f"/environment/{name}/__init__.py")
        if name in available:
            return SimpleNamespace(origin=f"/environment/{name}/__init__.py")
        return None

    monkeypatch.setattr(doctor.importlib.util, "find_spec", find_spec)
    monkeypatch.setattr(doctor.metadata, "version", lambda name: "1.2.3")
    monkeypatch.setattr(
        doctor.metadata,
        "packages_distributions",
        lambda: {"urllib3": ["urllib3"]},
    )
    monkeypatch.setattr(doctor, "is_browser_running", lambda browser: False)


def by_name(report: doctor.DoctorReport) -> dict[str, doctor.CheckResult]:
    return {check.name: check for check in report.checks}


def test_doctor_healthy_report_is_structured_json_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = prepare_workspace(tmp_path)
    patch_dependencies(monkeypatch)
    before = sorted((path.relative_to(tmp_path), path.stat().st_mtime_ns) for path in tmp_path.rglob("*"))

    report = run_doctor(settings)

    after = sorted((path.relative_to(tmp_path), path.stat().st_mtime_ns) for path in tmp_path.rglob("*"))
    assert report.healthy
    assert report.exit_code() == 0
    assert all(check.status in {CheckStatus.PASS, CheckStatus.SKIP} for check in report.checks)
    assert before == after
    payload = report.to_dict()
    assert payload["healthy"] is True
    assert payload["exit_code"] == 0
    json.dumps(payload)


def test_doctor_warning_exit_for_relevant_running_browser_and_stale_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = prepare_workspace(tmp_path)
    patch_dependencies(monkeypatch)
    monkeypatch.setattr(doctor, "is_browser_running", lambda browser: True)
    lock = settings.base_dir / "instagram" / "example" / "archive.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("locked", encoding="ascii")
    old = time.time() - 7200
    os.utime(lock, (old, old))

    report = run_doctor(settings)
    checks = by_name(report)

    assert not report.healthy
    assert report.exit_code() == 3
    assert checks["browser"].status is CheckStatus.WARN
    assert checks["archive_locks"].status is CheckStatus.WARN
    assert not any(check.status is CheckStatus.FAIL for check in report.checks)


def test_browser_check_is_skipped_when_valid_tiktok_cookie_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = prepare_workspace(tmp_path)
    patch_dependencies(monkeypatch)
    cookie = settings.cookies_dir / "tiktok_cookies.txt"
    cookie.write_text(
        ".tiktok.com\tTRUE\t/\tFALSE\t1700000000\tsessionid\tsecret\n",
        encoding="utf-8",
    )

    def unexpected_browser_probe(browser: str) -> bool:
        raise AssertionError(f"browser probe should be skipped: {browser}")

    monkeypatch.setattr(doctor, "is_browser_running", unexpected_browser_probe)
    report = run_doctor(settings)

    assert by_name(report)["browser"].status is CheckStatus.SKIP
    assert "secret" not in json.dumps(report.to_dict())


def test_doctor_failures_cover_config_workspace_dependency_and_cookie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_for_root(tmp_path)
    settings.cookies_dir.mkdir(parents=True)
    invalid = settings.cookies_dir / "instagram_cookies.txt"
    invalid.write_text("private-cookie-value", encoding="utf-8")
    patch_dependencies(monkeypatch, missing=frozenset({"gallery_dl"}))

    report = run_doctor(settings, config_error="bad configuration")
    checks = by_name(report)

    assert report.exit_code() == 1
    assert checks["config"].status is CheckStatus.FAIL
    assert checks["dependency.gallery_dl"].status is CheckStatus.FAIL
    assert checks["workspace.downloads"].status is CheckStatus.FAIL
    assert checks["cookie.instagram.instagram_cookies.txt"].status is CheckStatus.FAIL
    rendered = json.dumps(report.to_dict())
    assert "private-cookie-value" not in rendered
    assert all(check.remediation for check in report.checks if check.status is CheckStatus.FAIL)


def test_urllib3_conflict_is_reported_without_importing_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = prepare_workspace(tmp_path)
    patch_dependencies(monkeypatch, conflicts=frozenset({"niquests"}))

    report = run_doctor(settings)
    check = by_name(report)["urllib3"]

    assert check.status is CheckStatus.WARN
    assert "niquests" in check.message
    assert report.exit_code() == 3
