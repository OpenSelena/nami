import json
import os
import time
from pathlib import Path

import pytest

from nami.archive import (
    ArchiveBusyError,
    ArchiveContainmentError,
    ArchiveLock,
    archive_path,
    discover_archives,
    reset_archives,
)


def _create_archive(directory: Path, content: str = "entry\n") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = archive_path(directory)
    path.write_text(content, encoding="utf-8")
    return path


def test_archive_path_never_deletes_or_truncates(tmp_path: Path) -> None:
    directory = tmp_path / "instagram" / "nasa"
    existing = _create_archive(directory, "one\ntwo\n")
    assert archive_path(directory) == existing
    assert existing.read_text(encoding="utf-8") == "one\ntwo\n"


def test_discovery_is_deterministic_and_selector_is_contained(tmp_path: Path) -> None:
    x_archive = _create_archive(tmp_path / "x" / "nasa")
    instagram_archive = _create_archive(tmp_path / "instagram" / "natgeo")
    assert discover_archives(tmp_path) == (instagram_archive.resolve(), x_archive.resolve())
    assert discover_archives(tmp_path, "instagram") == (instagram_archive.resolve(),)

    for selector in ("../outside", "..\\outside", "C:\\outside", "/absolute"):
        with pytest.raises(ArchiveContainmentError):
            discover_archives(tmp_path, selector)


def test_reset_requires_explicit_scope_and_defaults_to_backup(tmp_path: Path) -> None:
    source = _create_archive(tmp_path / "instagram" / "nasa", "preserve me")
    with pytest.raises(ValueError, match="selector"):
        reset_archives(tmp_path)

    results = reset_archives(tmp_path, "instagram/nasa")
    assert len(results) == 1
    result = results[0]
    assert not source.exists()
    assert result.destination is not None
    assert result.destination.read_text(encoding="utf-8") == "preserve me"
    assert not result.deleted


def test_backup_does_not_overwrite_existing_backup(tmp_path: Path) -> None:
    source = _create_archive(tmp_path / "x" / "nasa", "new")
    first_backup = source.with_name("archive.txt.bak")
    first_backup.write_text("old", encoding="utf-8")
    result = reset_archives(tmp_path, all_archives=True)[0]
    assert result.destination == source.with_name("archive.txt.bak.1")
    assert first_backup.read_text(encoding="utf-8") == "old"


def test_reset_dry_run_preserves_archive_and_reports_action(tmp_path: Path) -> None:
    source = _create_archive(tmp_path / "facebook" / "meta")
    result = reset_archives(tmp_path, all_archives=True, dry_run=True)[0]
    assert source.exists()
    assert result.dry_run
    assert result.destination == source.with_name("archive.txt.bak")
    assert not result.destination.exists()


def test_permanent_deletion_requires_delete_flag(tmp_path: Path) -> None:
    source = _create_archive(tmp_path / "tiktok" / "creator")
    result = reset_archives(tmp_path, "tiktok", delete=True)[0]
    assert result.deleted
    assert result.destination is None
    assert not source.exists()


def test_archive_lock_contention_and_cleanup(tmp_path: Path) -> None:
    archive = tmp_path / "archive.txt"
    first = ArchiveLock(archive, timeout=0.1)
    second = ArchiveLock(archive, timeout=0)
    assert first.lock_path == tmp_path / "archive.lock"
    assert ArchiveLock(first.lock_path).lock_path == first.lock_path
    assert first.acquire().acquired
    assert first.lock_path.is_file()
    if os.name != "nt":
        assert first.lock_path.stat().st_mode & 0o777 == 0o600

    with pytest.raises(ArchiveBusyError):
        second.acquire()
    first.release()
    assert not first.lock_path.exists()
    with second:
        assert second.acquired
    assert not second.lock_path.exists()


def test_lock_release_checks_owner_token(tmp_path: Path) -> None:
    lock = ArchiveLock(tmp_path / "archive.txt")
    lock.acquire()
    lock.lock_path.write_text(
        json.dumps({"pid": os.getpid(), "created": time.time(), "token": "other"}),
        encoding="ascii",
    )
    lock.release()
    assert lock.lock_path.exists()


def test_stale_dead_process_lock_is_recovered(tmp_path: Path) -> None:
    lock = ArchiveLock(tmp_path / "archive.txt", timeout=0.1, stale_after=1)
    lock.lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock.lock_path.write_text(
        json.dumps({"pid": 999_999_999, "created": time.time() - 100, "token": "stale"}),
        encoding="ascii",
    )
    old = time.time() - 100
    os.utime(lock.lock_path, (old, old))

    lock.acquire()
    assert lock.acquired
    lock.release()
    assert not lock.lock_path.exists()
