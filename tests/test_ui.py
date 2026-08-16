from __future__ import annotations

from io import StringIO

from nami import ui
from nami.doctor import CheckResult, CheckStatus, DoctorReport
from nami.events import DownloadEvent
from nami.models import BatchResult, MediaKind, OperationResult, Outcome
from nami.targets import parse_target


def plain_console(stream: StringIO):
    return ui.make_console(file=stream, environ={"NO_COLOR": "1"})


def test_console_honors_no_color_over_force_color() -> None:
    stream = StringIO()
    console = ui.make_console(file=stream, environ={"NO_COLOR": "1", "FORCE_COLOR": "1"})
    console.print("literal")
    assert stream.getvalue() == "literal\n"
    assert "\x1b[" not in stream.getvalue()


def test_event_sink_renders_remote_markup_literals() -> None:
    stream = StringIO()
    sink = ui.RichEventSink(plain_console(stream))
    sink.emit(DownloadEvent("output", "[download] bad[/tag]", {"line": "ignored"}))
    sink.emit(DownloadEvent("retry", "try [bold]again[/bold]"))

    rendered = stream.getvalue()
    assert "[download] bad[/tag]" in rendered
    assert "try [bold]again[/bold]" in rendered
    assert "[retry]" in rendered


def test_batch_renderer_distinguishes_outcomes_and_keeps_messages_literal() -> None:
    target = parse_target("https://x.com/example")
    batch = BatchResult(
        (
            OperationResult(
                target,
                MediaKind.PHOTOS,
                Outcome.UNSUPPORTED,
                message="bad[/tag]",
            ),
            OperationResult(
                target,
                MediaKind.VIDEOS,
                Outcome.PARTIAL,
                message="[download] partial",
            ),
            OperationResult(
                target,
                MediaKind.STORIES,
                Outcome.FAILED,
                message="failed [red]literally[/red]",
            ),
        )
    )
    stream = StringIO()
    ui.render_batch_result(batch, plain_console(stream))

    rendered = stream.getvalue()
    assert "UNSUPPORTED" in rendered
    assert "PARTIAL" in rendered
    assert "FAILED" in rendered
    assert "bad[/tag]" in rendered
    assert "[download] partial" in rendered
    assert "[red]literally[/red]" in rendered


def test_doctor_renderer_keeps_external_text_literal() -> None:
    report = DoctorReport(
        (
            CheckResult(
                "config[/tag]",
                CheckStatus.FAIL,
                "broken [bold]value[/bold]",
                "fix [link]literally[/link]",
            ),
        )
    )
    stream = StringIO()
    ui.render_doctor_report(report, plain_console(stream))

    rendered = stream.getvalue()
    assert "config[/tag]" in rendered
    assert "broken [bold]value[/bold]" in rendered
    assert "fix [link]literally[/link]" in rendered
