from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from nami.events import CallbackEventSink
from nami.process import CommandSpec, SubprocessRunner


def python_command(source: str, *arguments: str, timeout: float = 2.0) -> CommandSpec:
    return CommandSpec((sys.executable, "-c", source, *arguments), timeout)


def test_streams_output_before_process_completion() -> None:
    observed: list[tuple[str, float]] = []
    started = time.monotonic()
    sink = CallbackEventSink(lambda event: observed.append((event.message, time.monotonic() - started)))

    result = SubprocessRunner().run(
        python_command("import time; print('first', flush=True); time.sleep(0.35); print('second')"),
        event_sink=sink,
    )

    assert result.returncode == 0
    assert [line for line, _ in observed] == ["first", "second"]
    assert observed[0][1] < 0.3
    assert result.duration_seconds >= 0.3


def test_silent_child_hits_wall_clock_timeout_promptly() -> None:
    started = time.monotonic()
    result = SubprocessRunner(terminate_grace_seconds=0.1).run(
        python_command("import time; time.sleep(10)", timeout=0.2)
    )

    assert result.timed_out is True
    assert result.cancelled is False
    assert time.monotonic() - started < 2.0


def test_timeout_terminates_descendant_process(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-survived"
    child_source = "import pathlib,sys,time; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('alive')"
    parent_source = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
        "print('spawned', flush=True); time.sleep(10)"
    )

    result = SubprocessRunner(terminate_grace_seconds=0.1).run(
        python_command(parent_source, child_source, str(marker), timeout=0.2)
    )
    time.sleep(0.9)

    assert result.timed_out is True
    assert not marker.exists()


def test_callback_exception_terminates_process_tree(tmp_path: Path) -> None:
    marker = tmp_path / "callback-descendant-survived"
    child_source = "import pathlib,sys,time; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('alive')"
    parent_source = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
        "print('ready', flush=True); time.sleep(10)"
    )

    def fail_callback(event: object) -> None:
        del event
        raise RuntimeError("event handler failed")

    with pytest.raises(RuntimeError, match="event handler failed"):
        SubprocessRunner(terminate_grace_seconds=0.1).run(
            python_command(parent_source, child_source, str(marker)),
            event_sink=CallbackEventSink(fail_callback),
        )
    time.sleep(0.9)

    assert not marker.exists()


def test_cancellation_event_returns_cancelled_result() -> None:
    cancellation = threading.Event()
    timer = threading.Timer(0.15, cancellation.set)
    timer.start()
    try:
        result = SubprocessRunner(terminate_grace_seconds=0.1).run(
            python_command("import time; time.sleep(10)"),
            cancel_event=cancellation,
        )
    finally:
        timer.cancel()

    assert result.cancelled is True
    assert result.timed_out is False


def test_arguments_are_not_interpreted_by_a_shell(tmp_path: Path) -> None:
    marker = tmp_path / "injected"
    hostile = f"; echo owned > {marker}"

    result = SubprocessRunner().run(python_command("import sys; print(sys.argv[1])", hostile))

    assert result.returncode == 0
    assert hostile in result.lines
    assert not marker.exists()


def test_output_redacts_cookie_content_and_url_queries() -> None:
    emitted: list[str] = []
    result = SubprocessRunner().run(
        python_command(
            "print('https://example.test/video?token=query-secret'); "
            "print('Cookie: session=cookie-secret; csrf=also-secret')"
        ),
        event_sink=CallbackEventSink(lambda event: emitted.append(event.message)),
    )

    combined = "\n".join((*result.lines, *emitted))
    assert "query-secret" not in combined
    assert "cookie-secret" not in combined
    assert "also-secret" not in combined
    assert "?<redacted>" in combined
    assert "<credential header redacted>" in combined


def test_command_repr_redacts_cookie_path_and_url_query() -> None:
    spec = CommandSpec(
        (
            "downloader",
            "--cookies",
            "/private/session-cookies.txt",
            "https://example.test/video?token=secret#fragment",
        ),
        1,
        environment={"SECRET": "value"},
    )

    representation = repr(spec)
    assert "session-cookies" not in representation
    assert "token=secret" not in representation
    assert "SECRET" not in representation
    assert "<redacted>" in representation
