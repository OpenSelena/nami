"""Safe, streaming subprocess execution for downloader engines."""

from __future__ import annotations

import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import BinaryIO, final

from nami.events import DownloadEvent, EventSink, NullEventSink

_URL_RE = re.compile(r"(?P<url>https?://[^\s\"'<>]+)", re.IGNORECASE)
_SECRET_RE = re.compile(
    r"(?i)\b(cookie|authorization|password|passwd|token|api[-_]?key)"
    r"(\s*[:=]\s*)([^\s;,]+)"
)
_CREDENTIAL_HEADER_RE = re.compile(r"(?i)\b(?:cookie|set-cookie|authorization)\s*:\s*[^\r\n]*")
_SECRET_OPTIONS = frozenset(
    {
        "--add-header",
        "--cookies",
        "--password",
        "--username",
        "--video-password",
    }
)


def redact_text(text: str) -> str:
    """Remove common credentials and URL query/fragment data from diagnostics."""

    cookie_fields = text.split("\t")
    if (
        len(cookie_fields) >= 7
        and cookie_fields[1].casefold() in {"true", "false"}
        and cookie_fields[3].casefold() in {"true", "false"}
    ):
        return "<cookie data redacted>"

    def redact_url(match: re.Match[str]) -> str:
        url = match.group("url")
        cut_at = len(url)
        for separator in ("?", "#"):
            position = url.find(separator)
            if position >= 0:
                cut_at = min(cut_at, position)
        if cut_at == len(url):
            return url
        return f"{url[:cut_at]}?<redacted>"

    without_headers = _CREDENTIAL_HEADER_RE.sub("<credential header redacted>", text)
    without_queries = _URL_RE.sub(redact_url, without_headers)
    return _SECRET_RE.sub(r"\1\2<redacted>", without_queries)


def _redacted_argv(argv: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    redact_next = False
    for argument in argv:
        if redact_next:
            result.append("<redacted>")
            redact_next = False
            continue
        if argument in _SECRET_OPTIONS:
            result.append(argument)
            redact_next = True
            continue
        if argument.startswith("--cookies="):
            result.append("--cookies=<redacted>")
            continue
        result.append(redact_text(argument))
    return tuple(result)


@dataclass(frozen=True, slots=True, repr=False)
class CommandSpec:
    """A subprocess invocation. Arguments are always passed without a shell."""

    argv: tuple[str, ...]
    timeout_seconds: float
    cwd: Path | None = None
    environment: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        argv = tuple(self.argv)
        if not argv:
            raise ValueError("argv must contain at least one string")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        object.__setattr__(self, "argv", argv)
        if self.cwd is not None:
            object.__setattr__(self, "cwd", Path(self.cwd))
        if self.environment is not None:
            environment = {str(key): str(value) for key, value in self.environment.items()}
            object.__setattr__(self, "environment", MappingProxyType(environment))

    def __repr__(self) -> str:
        environment = None if self.environment is None else f"<{len(self.environment)} variables>"
        return (
            "CommandSpec("
            f"argv={_redacted_argv(self.argv)!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, "
            f"cwd={self.cwd!r}, environment={environment})"
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The bounded diagnostic result of a command execution."""

    returncode: int
    output_tail: str
    lines: tuple[str, ...]
    timed_out: bool
    cancelled: bool
    duration_seconds: float


@final
class _ReaderFailure:
    def __init__(self, error: BaseException) -> None:
        self.error: BaseException = error


@final
class _ReaderDone:
    pass


_READER_DONE = _ReaderDone()
_QueueItem = bytes | _ReaderFailure | _ReaderDone


@final
class SubprocessRunner:
    """Run commands with streaming output, bounded capture, and tree cleanup."""

    def __init__(
        self,
        *,
        max_lines: int = 1_000,
        max_tail_bytes: int = 64 * 1024,
        poll_interval_seconds: float = 0.05,
        terminate_grace_seconds: float = 1.0,
    ) -> None:
        if max_lines <= 0 or max_tail_bytes <= 0:
            raise ValueError("capture bounds must be greater than zero")
        if poll_interval_seconds <= 0 or terminate_grace_seconds < 0:
            raise ValueError("poll interval must be positive and grace must be non-negative")
        self._max_lines: int = max_lines
        self._max_tail_bytes: int = max_tail_bytes
        self._poll_interval_seconds: float = poll_interval_seconds
        self._terminate_grace_seconds: float = terminate_grace_seconds

    def run(
        self,
        spec: CommandSpec,
        *,
        event_sink: EventSink | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CommandResult:
        """Execute *spec*, emitting each merged output line as soon as it arrives."""

        sink = event_sink or NullEventSink()
        environment = None
        if spec.environment is not None:
            environment = os.environ.copy()
            environment.update(spec.environment)

        started_at = time.monotonic()
        if sys.platform == "win32":
            process: subprocess.Popen[bytes] = subprocess.Popen(
                spec.argv,
                cwd=spec.cwd,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                shell=False,
                bufsize=0,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            process = subprocess.Popen(
                spec.argv,
                cwd=spec.cwd,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                shell=False,
                bufsize=0,
                start_new_session=True,
            )
        if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
            self._terminate_tree(process)
            raise RuntimeError("subprocess stdout pipe was not created")

        output_queue: queue.Queue[_QueueItem] = queue.Queue(maxsize=256)
        stop_reader = threading.Event()
        reader = threading.Thread(
            target=self._read_output,
            args=(process.stdout, output_queue, stop_reader),
            name=f"nami-output-{process.pid}",
            daemon=True,
        )
        reader.start()

        captured_lines: deque[str] = deque(maxlen=self._max_lines)
        tail_lines: deque[tuple[str, int]] = deque()
        tail_size = 0
        timed_out = False
        cancelled = False
        reader_done = False
        deadline = started_at + spec.timeout_seconds

        def capture(raw_line: bytes, *, emit: bool) -> None:
            nonlocal tail_size
            line = redact_text(raw_line.decode("utf-8", errors="replace").rstrip("\r\n"))
            captured_lines.append(line)
            encoded_size = len(line.encode("utf-8")) + 1
            tail_lines.append((line, encoded_size))
            tail_size += encoded_size
            while tail_lines and tail_size > self._max_tail_bytes:
                _, removed_size = tail_lines.popleft()
                tail_size -= removed_size
            if emit:
                sink.emit(DownloadEvent("output", line, {"line": line}))

        try:
            while True:
                now = time.monotonic()
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
                if now >= deadline:
                    timed_out = True
                    break

                wait_seconds = min(self._poll_interval_seconds, max(0.0, deadline - now))
                try:
                    item = output_queue.get(timeout=wait_seconds)
                except queue.Empty:
                    continue

                if item is _READER_DONE:
                    reader_done = True
                elif isinstance(item, _ReaderFailure):
                    raise item.error
                elif isinstance(item, bytes):
                    capture(item, emit=True)

                if reader_done and process.poll() is not None and output_queue.empty():
                    break
        except KeyboardInterrupt:
            cancelled = True
        except BaseException:
            self._terminate_tree(process)
            raise
        finally:
            if timed_out or cancelled:
                self._terminate_tree(process)

            if process.poll() is None:
                self._terminate_tree(process)
            else:
                process.wait()

            stop_reader.set()
            try:
                process.stdout.close()
            except OSError:
                pass
            reader.join(timeout=max(1.0, self._terminate_grace_seconds))

            while True:
                try:
                    item = output_queue.get_nowait()
                except queue.Empty:
                    break
                if isinstance(item, bytes):
                    capture(item, emit=False)

        duration = time.monotonic() - started_at
        returncode = process.returncode if process.returncode is not None else -1
        return CommandResult(
            returncode=returncode,
            output_tail="\n".join(line for line, _ in tail_lines),
            lines=tuple(captured_lines),
            timed_out=timed_out,
            cancelled=cancelled,
            duration_seconds=duration,
        )

    @staticmethod
    def _read_output(
        stream: BinaryIO,
        output_queue: queue.Queue[_QueueItem],
        stop_reader: threading.Event,
    ) -> None:
        try:
            while not stop_reader.is_set():
                line = stream.readline()
                if not line:
                    break
                SubprocessRunner._put_reader_item(output_queue, line, stop_reader)
        except (OSError, ValueError) as error:
            SubprocessRunner._put_reader_item(output_queue, _ReaderFailure(error), stop_reader)
        finally:
            SubprocessRunner._put_reader_item(output_queue, _READER_DONE, stop_reader)

    @staticmethod
    def _put_reader_item(
        output_queue: queue.Queue[_QueueItem],
        item: _QueueItem,
        stop_reader: threading.Event,
    ) -> None:
        while not stop_reader.is_set():
            try:
                output_queue.put(item, timeout=0.05)
                return
            except queue.Full:
                continue

    def _terminate_tree(self, process: subprocess.Popen[bytes]) -> None:
        """Terminate the process group, escalate, and always reap the child."""

        if sys.platform == "win32":
            self._taskkill(process.pid, force=False)
            self._wait_for_process(process, self._terminate_grace_seconds)
            self._taskkill(process.pid, force=True)
        else:
            process_group = process.pid
            try:
                os.killpg(process_group, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                process.terminate()
            self._wait_for_group(process_group, self._terminate_grace_seconds)
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                process.kill()

        try:
            process.wait(timeout=max(1.0, self._terminate_grace_seconds))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    @staticmethod
    def _taskkill(pid: int, *, force: bool) -> None:
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        try:
            subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    @staticmethod
    def _wait_for_process(process: subprocess.Popen[bytes], seconds: float) -> None:
        if seconds <= 0:
            return
        try:
            process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def _wait_for_group(process_group: int, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                return
            time.sleep(0.02)
