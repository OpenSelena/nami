"""Archive and deduplication state management for Nami."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


class ArchiveLock:
    """Simple directory-based lock file helper for archive safety."""

    def __init__(self, directory: Path, lock_name: str = "archive.lock") -> None:
        self.directory = Path(directory)
        self.lock_file = self.directory / lock_name
        self.acquired = False

    def acquire(self, timeout: float = 10.0) -> bool:
        self.directory.mkdir(parents=True, exist_ok=True)
        start = time.time()
        while time.time() - start < timeout:
            try:
                # O_CREAT | O_EXCL ensures atomic creation
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"PID:{os.getpid()}\n".encode("utf-8"))
                os.close(fd)
                self.acquired = True
                return True
            except FileExistsError:
                time.sleep(0.2)
            except OSError:
                return False
        return False

    def release(self) -> None:
        if self.acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except OSError:
                pass
            self.acquired = False

    def __enter__(self) -> ArchiveLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object | None) -> None:
        self.release()


def init_archive_dir(directory: Path) -> Path:
    """
    Ensure target directory exists and return the archive file path.
    Does NOT delete existing archive file even if media directory is empty,
    preserving historical download records.
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / "archive.txt"


def reset_archive(directory: Path) -> bool:
    """Explicitly delete archive file when requested by user."""
    archive_path = Path(directory) / "archive.txt"
    if archive_path.exists():
        try:
            archive_path.unlink()
            return True
        except OSError:
            return False
    return False
