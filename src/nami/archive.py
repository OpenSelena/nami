"""Safe archive discovery, explicit reset, and inter-process locking."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

_ARCHIVE_NAME = "archive.txt"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class ArchiveError(RuntimeError):
    """Base class for archive safety failures."""


class ArchiveContainmentError(ArchiveError):
    """Raised when an archive or selector escapes its configured root."""


class ArchiveBusyError(ArchiveError):
    """Raised when an archive lock cannot be acquired before its timeout."""


@dataclass(frozen=True)
class ArchiveReset:
    source: Path
    destination: Path | None
    deleted: bool
    dry_run: bool


def archive_path(directory: Path | str) -> Path:
    """Return an archive path without creating, truncating, or deleting anything."""
    return Path(directory) / _ARCHIVE_NAME


def discover_archives(base_dir: Path | str, selector: Path | str | None = None) -> tuple[Path, ...]:
    """Discover contained archive files, optionally below an exact selector prefix."""
    root = Path(base_dir).expanduser().resolve()
    selected = _validate_selector(selector) if selector is not None else None
    archives: list[Path] = []
    if not root.exists():
        return ()

    for candidate in root.rglob(_ARCHIVE_NAME):
        resolved = candidate.resolve()
        _require_contained(root, resolved)
        try:
            relative_parent = resolved.parent.relative_to(root)
        except ValueError as exc:
            raise ArchiveContainmentError(f"archive escapes base directory: {candidate}") from exc
        if selected is not None and not _matches_selector(relative_parent, selected):
            continue
        if resolved.is_file():
            archives.append(resolved)
    return tuple(sorted(archives, key=lambda item: item.as_posix().casefold()))


def reset_archives(
    base_dir: Path | str,
    selector: Path | str | None = None,
    *,
    all_archives: bool = False,
    delete: bool = False,
    dry_run: bool = False,
) -> tuple[ArchiveReset, ...]:
    """Explicitly back up (default) or delete selected archives.

    A selector or ``all_archives=True`` is mandatory. Backups never overwrite an
    existing file; permanent deletion requires the separate ``delete=True`` flag.
    """
    if selector is None and not all_archives:
        raise ValueError("reset requires a selector or all_archives=True")
    if selector is not None and all_archives:
        raise ValueError("use either a selector or all_archives=True, not both")

    archives = discover_archives(base_dir, None if all_archives else selector)
    results: list[ArchiveReset] = []
    for source in archives:
        if delete:
            if not dry_run:
                source.unlink()
            results.append(ArchiveReset(source, None, deleted=True, dry_run=dry_run))
            continue

        destination = _next_backup_path(source)
        if not dry_run:
            source.rename(destination)
        results.append(ArchiveReset(source, destination, deleted=False, dry_run=dry_run))
    return tuple(results)


class ArchiveLock:
    """Atomic owner-checked file lock with conservative stale recovery."""

    def __init__(
        self,
        archive_or_directory: Path | str,
        *,
        timeout: float = 10.0,
        poll_interval: float = 0.05,
        stale_after: float = 3600.0,
    ) -> None:
        value = Path(archive_or_directory)
        if value.suffix == ".lock":
            self.lock_path = value
        elif value.name == _ARCHIVE_NAME:
            self.lock_path = value.with_name("archive.lock")
        else:
            self.lock_path = value / "archive.lock"
        if timeout < 0 or poll_interval <= 0 or stale_after < 0:
            raise ValueError("lock timing values must be non-negative")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.stale_after = stale_after
        self._token: str | None = None

    @property
    def acquired(self) -> bool:
        return self._token is not None

    def acquire(self, timeout: float | None = None) -> ArchiveLock:
        wait_for = self.timeout if timeout is None else timeout
        if wait_for < 0:
            raise ValueError("timeout must be non-negative")
        if self.acquired:
            raise RuntimeError("archive lock is already acquired by this object")

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + wait_for
        token = uuid.uuid4().hex
        while True:
            try:
                self._create_lock(token)
            except FileExistsError as error:
                self._recover_stale_lock()
                if time.monotonic() >= deadline:
                    raise ArchiveBusyError(f"archive is locked: {self.lock_path}") from error
                time.sleep(min(self.poll_interval, max(0.0, deadline - time.monotonic())))
                continue
            self._token = token
            return self

    def release(self) -> None:
        token = self._token
        if token is None:
            return
        try:
            owner = self._read_owner()
            if owner is not None and owner.get("token") == token:
                self.lock_path.unlink(missing_ok=True)
        finally:
            self._token = None

    def __enter__(self) -> ArchiveLock:
        return self.acquire()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()

    def _create_lock(self, token: str) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(self.lock_path, flags, 0o600)
        try:
            try:
                os.chmod(self.lock_path, 0o600)
            except OSError:
                pass
            payload = json.dumps(
                {"pid": os.getpid(), "created": time.time(), "token": token},
                separators=(",", ":"),
            ).encode("ascii")
            os.write(fd, payload)
            os.fsync(fd)
        except Exception:
            try:
                self.lock_path.unlink()
            except OSError:
                pass
            raise
        finally:
            os.close(fd)

    def _read_owner(self) -> dict[str, object] | None:
        try:
            raw = self.lock_path.read_text(encoding="ascii")
            value = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _recover_stale_lock(self) -> None:
        try:
            age = max(0.0, time.time() - self.lock_path.stat().st_mtime)
        except FileNotFoundError:
            return
        except OSError:
            return
        if age < self.stale_after:
            return

        owner = self._read_owner()
        if owner is not None:
            pid = owner.get("pid")
            created = owner.get("created")
            if isinstance(created, (int, float)):
                age = max(age, time.time() - float(created))
            if age < self.stale_after or not isinstance(pid, int) or _pid_is_running(pid):
                return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _validate_selector(selector: Path | str) -> tuple[str, ...]:
    raw = str(selector).strip()
    if (
        not raw
        or raw.startswith(("/", "\\"))
        or Path(raw).is_absolute()
        or _WINDOWS_DRIVE.match(raw)
        or "\\" in raw
        or _CONTROL.search(raw)
    ):
        raise ArchiveContainmentError("archive selector must be a safe relative path")
    parts = tuple(part for part in raw.split("/") if part)
    if not parts or any(part in {".", ".."} or ":" in part for part in parts):
        raise ArchiveContainmentError("archive selector escapes the base directory")
    return parts


def _matches_selector(relative_parent: Path, selector: tuple[str, ...]) -> bool:
    parts = relative_parent.parts
    return len(parts) >= len(selector) and parts[: len(selector)] == selector


def _require_contained(root: Path, candidate: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ArchiveContainmentError(f"archive escapes base directory: {candidate}") from exc


def _next_backup_path(source: Path) -> Path:
    first = source.with_name(f"{source.name}.bak")
    if not first.exists():
        return first
    counter = 1
    while True:
        candidate = source.with_name(f"{source.name}.bak.{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
