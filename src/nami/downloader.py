"""Subprocess management and tool execution for Nami."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from nami.config import DEFAULT_TIMEOUT, UA


def kill_process_tree(proc: subprocess.Popen[str]) -> None:
    """Terminate process tree reliably across Windows and Unix."""
    if proc.poll() is not None:
        return

    pid = proc.pid
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def looks_like_media_output_line(line: str) -> bool:
    from nami.config import MEDIA_EXTS
    candidate = line.strip()
    if candidate.startswith("#"):
        candidate = candidate[1:].strip()
    if not candidate:
        return False
    has_sep = ("/" in candidate or "\\" in candidate)
    ext = os.path.splitext(candidate)[1].lower()
    return has_sep and ext in MEDIA_EXTS


def parse_output_counts(output: str) -> tuple[int, int]:
    """Parse output text to calculate (items_downloaded, items_skipped)."""
    from nami.config import MEDIA_EXTS
    downloaded = 0
    skipped = 0

    for line in output.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if line_stripped.startswith("#"):
            candidate = line_stripped[1:].strip()
            ext = os.path.splitext(candidate)[1].lower()
            if ext in MEDIA_EXTS or "/" in candidate or "\\" in candidate:
                skipped += 1
        elif "has already been downloaded" in line_stripped.lower() or "archive" in line_stripped.lower():
            skipped += 1
        elif looks_like_media_output_line(line_stripped):
            downloaded += 1
        elif line_stripped.startswith("[download]") and ("100%" in line_stripped or "destination:" in line_stripped.lower()):
            downloaded += 1

    return downloaded, skipped


def run_command(
    cmd: list[str],
    silent_log_path: str | Path | None = None,
    progress_obj: Any = None,
    active_task_id: Any = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """
    Run external downloader CLI tool with process tree protection and timeout enforcement.
    Returns tuple of (returncode, stdout, stderr).
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    popen_kwargs: dict[str, Any] = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    if silent_log_path:
        log_dir = Path(silent_log_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(silent_log_path, "w", encoding="utf-8", errors="replace") as f:
                proc = subprocess.Popen(
                    cmd, stdout=f, stderr=subprocess.STDOUT, **popen_kwargs
                )
                try:
                    proc.wait(timeout=timeout)
                    return proc.returncode, "", ""
                except subprocess.TimeoutExpired:
                    kill_process_tree(proc)
                    return 124, "", f"Timed out after {timeout}s"
        except Exception as e:
            return 1, "", str(e)

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            **popen_kwargs
        )
        try:
            stdout_data, _ = proc.communicate(timeout=timeout)
            stdout_data = stdout_data or ""
            items_processed = 0
            for line in stdout_data.splitlines():
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                if looks_like_media_output_line(line_stripped):
                    items_processed += 1
                    file_name = os.path.basename(line_stripped.lstrip("#").strip())
                    if progress_obj is not None and active_task_id is not None:
                        status_msg = (
                            f"Checking: {file_name[:25]}..."
                            if line_stripped.startswith("#")
                            else f"Downloaded: {file_name[:25]}..."
                        )
                        progress_obj.update(
                            active_task_id,
                            completed=items_processed,
                            total=None,
                            status=status_msg,
                        )

            return proc.returncode, stdout_data, ""
        except subprocess.TimeoutExpired:
            kill_process_tree(proc)
            return 124, "", f"Timed out after {timeout}s"
        except KeyboardInterrupt:
            kill_process_tree(proc)
            raise
    except KeyboardInterrupt:
        raise
    except Exception as e:
        return 1, "", str(e)


def download_gd(
    directory: Path,
    filter_str: str | None,
    cookies_args: list[str],
    url: str,
    sleep_time: str = "5",
    silent: bool = False,
    progress_obj: Any = None,
    active_task_id: Any = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "gallery_dl",
        "-D", str(dir_path),
        "-o", f"user-agent={UA}",
        "--download-archive", str(dir_path / "archive.txt"),
        "--sleep-request", sleep_time,
    ]
    if filter_str:
        cmd.extend(["--filter", filter_str])
    cmd.extend(cookies_args)
    cmd.append(url)
    log_path = str(dir_path / "lastrun.log") if silent else None
    return run_command(
        cmd, silent_log_path=log_path,
        progress_obj=progress_obj, active_task_id=active_task_id,
        timeout=timeout
    )


def download_yt(
    directory: Path,
    cookies_args: list[str],
    url: str,
    silent: bool = False,
    progress_obj: Any = None,
    active_task_id: Any = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-o", str(dir_path / "%(title)s.%(ext)s"),
        "--no-playlist",
        "--user-agent", UA,
        "--download-archive", str(dir_path / "archive.txt"),
    ]
    cmd.extend(cookies_args)
    cmd.append(url)
    log_path = str(dir_path / "lastrun.log") if silent else None
    return run_command(
        cmd, silent_log_path=log_path,
        progress_obj=progress_obj, active_task_id=active_task_id,
        timeout=timeout
    )
