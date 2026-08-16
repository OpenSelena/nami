from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from nami.archive import ArchiveLock
from nami.auth import AuthMode, AuthSpec
from nami.config import Settings, settings_for_root
from nami.engines.base import EngineAnalysis, EngineRequest
from nami.events import CallbackEventSink, DownloadEvent, EventSink
from nami.models import FailureKind, MediaKind, Outcome
from nami.planner import DownloadRequest, build_plan
from nami.process import CommandResult, CommandSpec
from nami.retry import RetryDecision, RetryPolicy
from nami.service import NamiService
from nami.targets import parse_target


def command_result(
    returncode: int = 0,
    *lines: str,
    timed_out: bool = False,
    cancelled: bool = False,
) -> CommandResult:
    return CommandResult(
        returncode=returncode,
        output_tail="\n".join(lines),
        lines=tuple(lines),
        timed_out=timed_out,
        cancelled=cancelled,
        duration_seconds=0.01,
    )


class FakeEngine:
    def __init__(self, name: str, *, supported: bool = True) -> None:
        self.name: str = name
        self.supported: bool = supported
        self.requests: list[EngineRequest] = []

    def supports(self, target: object, media: object) -> bool:
        del target, media
        return self.supported

    def build_command(self, request: EngineRequest) -> CommandSpec:
        self.requests.append(request)
        return CommandSpec(
            (self.name, request.auth.mode.value, request.url),
            request.timeout_seconds,
        )

    def analyze_output(self, lines: Iterable[str]) -> EngineAnalysis:
        downloaded = 0
        archived = 0
        for line in lines:
            if line.startswith("downloaded="):
                downloaded += int(line.partition("=")[2])
            elif line.startswith("archived="):
                archived += int(line.partition("=")[2])
        return EngineAnalysis(downloaded, archived)


class FixedRetryPolicy(RetryPolicy):
    def __init__(self, decision: RetryDecision) -> None:
        super().__init__()
        self.fixed_decision: RetryDecision = decision

    def decide(  # pyright: ignore[reportImplicitOverride]
        self,
        failure_kind: FailureKind,
        attempt: int = 1,
        auth_supplied: bool = False,
        anonymous_retry_used: bool = False,
        alternate_available: bool = False,
    ) -> RetryDecision:
        del (
            failure_kind,
            attempt,
            auth_supplied,
            anonymous_retry_used,
            alternate_available,
        )
        return self.fixed_decision


class FakeRunner:
    def __init__(
        self,
        results: list[CommandResult] | None = None,
        handler: Callable[[CommandSpec], CommandResult] | None = None,
    ) -> None:
        self.results: list[CommandResult] = list(results or [])
        self.handler: Callable[[CommandSpec], CommandResult] | None = handler
        self.calls: list[CommandSpec] = []
        self.sinks: list[EventSink | None] = []

    def run(
        self,
        spec: CommandSpec,
        *,
        event_sink: EventSink | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CommandResult:
        del cancel_event
        self.calls.append(spec)
        self.sinks.append(event_sink)
        if self.handler is not None:
            return self.handler(spec)
        if not self.results:
            raise AssertionError("unexpected extra command run")
        return self.results.pop(0)


def request_for(
    tmp_path: Path,
    media: tuple[MediaKind, ...] = (MediaKind.PHOTOS,),
    url: str = "https://www.instagram.com/example/",
) -> tuple[DownloadRequest, Settings]:
    settings = settings_for_root(tmp_path)
    return DownloadRequest((parse_target(url),), media, settings), settings


def service_with(
    runner: FakeRunner,
    engines: tuple[FakeEngine, ...],
    *,
    policy: RetryPolicy | None = None,
    sleeper: Callable[[float], None] | None = None,
    auth: AuthSpec | None = None,
    events: list[DownloadEvent] | None = None,
) -> NamiService:
    captured = events if events is not None else []
    return NamiService(
        engines={engine.name: engine for engine in engines},
        runner=runner,
        policy=policy or RetryPolicy(jitter=lambda: 0),
        sleeper=sleeper or (lambda delay: None),
        event_sink=CallbackEventSink(captured.append),
        auth_resolver=lambda platform, settings: auth or AuthSpec(AuthMode.NONE),
    )


def test_successful_final_network_retry_is_honored_without_extra_run(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            command_result(1, "Unable to connect"),
            command_result(1, "connection reset"),
            command_result(0, "downloaded=2"),
        ]
    )
    engine = FakeEngine("gallery-dl")
    sleeps: list[float] = []
    events: list[DownloadEvent] = []
    service = service_with(
        runner,
        (engine,),
        policy=RetryPolicy(max_attempts=3, jitter=lambda: 0),
        sleeper=sleeps.append,
        auth=AuthSpec(AuthMode.BROWSER, browser="firefox"),
        events=events,
    )

    batch = service.execute(request_for(tmp_path)[0])

    result = batch.results[0]
    assert result.outcome is Outcome.DOWNLOADED
    assert result.downloaded_count == 2
    assert len(result.attempts) == 3
    assert len(runner.calls) == 3
    assert sleeps == [1, 2]
    assert [item.auth.mode for item in engine.requests] == [AuthMode.BROWSER] * 3
    assert [event.kind for event in events] == [
        "start",
        "retry",
        "start",
        "retry",
        "start",
        "result",
    ]
    _ = json.dumps([{"kind": event.kind, "data": event.data} for event in events])


def test_no_sleep_after_final_transient_failure_and_no_engine_fallback(
    tmp_path: Path,
) -> None:
    runner = FakeRunner([command_result(1, "Unable to connect"), command_result(1, "read timed out")])
    gallery = FakeEngine("gallery-dl")
    alternate = FakeEngine("yt-dlp")
    sleeps: list[float] = []
    service = service_with(
        runner,
        (gallery, alternate),
        policy=RetryPolicy(max_attempts=2, jitter=lambda: 0),
        sleeper=sleeps.append,
    )

    result = service.execute(
        request_for(
            tmp_path,
            media=(MediaKind.VIDEOS,),
            url="https://x.com/example",
        )[0]
    ).results[0]

    assert result.outcome is Outcome.FAILED
    assert result.failure_kind is FailureKind.NETWORK
    assert len(runner.calls) == 2
    assert sleeps == [1]
    assert alternate.requests == []


def test_rate_limit_stops_immediately_without_fallback_or_sleep(tmp_path: Path) -> None:
    runner = FakeRunner([command_result(1, "HTTP Error 429: Too Many Requests")])
    gallery = FakeEngine("gallery-dl")
    alternate = FakeEngine("yt-dlp")
    sleeps: list[float] = []
    service = service_with(runner, (gallery, alternate), sleeper=sleeps.append)

    result = service.execute(
        request_for(
            tmp_path,
            media=(MediaKind.VIDEOS,),
            url="https://x.com/example",
        )[0]
    ).results[0]

    assert result.failure_kind is FailureKind.RATE_LIMIT
    assert len(runner.calls) == 1
    assert alternate.requests == []
    assert sleeps == []


def test_explicit_auth_failure_gets_one_anonymous_attempt_and_no_fallback(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            command_result(1, "login required"),
            command_result(1, "unsupported URL"),
        ]
    )
    gallery = FakeEngine("gallery-dl")
    alternate = FakeEngine("yt-dlp")
    service = service_with(
        runner,
        (gallery, alternate),
        auth=AuthSpec(AuthMode.COOKIE_FILE, cookie_file=tmp_path / "cookies.txt"),
    )

    result = service.execute(
        request_for(
            tmp_path,
            media=(MediaKind.VIDEOS,),
            url="https://x.com/example",
        )[0]
    ).results[0]

    assert result.outcome is Outcome.FAILED
    assert [item.auth.mode for item in gallery.requests] == [
        AuthMode.COOKIE_FILE,
        AuthMode.NONE,
    ]
    assert len(runner.calls) == 2
    assert alternate.requests == []


def test_anonymous_auth_failure_does_not_get_anonymous_retry(tmp_path: Path) -> None:
    runner = FakeRunner([command_result(1, "authentication required")])
    engine = FakeEngine("gallery-dl")

    result = service_with(runner, (engine,)).execute(request_for(tmp_path)[0]).results[0]

    assert result.failure_kind is FailureKind.AUTH
    assert len(runner.calls) == 1


def test_extractor_failure_is_the_only_cross_engine_fallback(tmp_path: Path) -> None:
    runner = FakeRunner([command_result(1, "Unsupported URL"), command_result(0, "archived=3")])
    gallery = FakeEngine("gallery-dl")
    alternate = FakeEngine("yt-dlp")
    service = service_with(runner, (gallery, alternate))

    result = service.execute(
        request_for(
            tmp_path,
            media=(MediaKind.VIDEOS,),
            url="https://x.com/example",
        )[0]
    ).results[0]

    assert result.outcome is Outcome.UP_TO_DATE
    assert result.existing_count == 3
    assert [attempt.extractor for attempt in result.attempts] == [
        "gallery-dl",
        "yt-dlp",
    ]
    assert len(runner.calls) == 2


def test_service_rejects_unsafe_actions_from_injected_policy(tmp_path: Path) -> None:
    runner = FakeRunner([command_result(1, "HTTP Error 429")])
    sleeps: list[float] = []
    service = service_with(
        runner,
        (FakeEngine("gallery-dl"), FakeEngine("yt-dlp")),
        policy=FixedRetryPolicy(RetryDecision(retry=True, retry_same_engine=True, delay_seconds=10)),
        sleeper=sleeps.append,
    )

    result = service.execute(
        request_for(
            tmp_path,
            media=(MediaKind.VIDEOS,),
            url="https://x.com/example",
        )[0]
    ).results[0]

    assert result.failure_kind is FailureKind.RATE_LIMIT
    assert len(runner.calls) == 1
    assert sleeps == []


def test_unsupported_injected_engine_uses_declared_extractor_fallback(
    tmp_path: Path,
) -> None:
    runner = FakeRunner([command_result(0, "downloaded=1")])
    gallery = FakeEngine("gallery-dl", supported=False)
    alternate = FakeEngine("yt-dlp")

    result = (
        service_with(runner, (gallery, alternate))
        .execute(
            request_for(
                tmp_path,
                media=(MediaKind.VIDEOS,),
                url="https://x.com/example",
            )[0]
        )
        .results[0]
    )

    assert result.outcome is Outcome.DOWNLOADED
    assert [attempt.extractor for attempt in result.attempts] == [
        "gallery-dl",
        "yt-dlp",
    ]
    assert len(runner.calls) == 1


def test_instagram_feed_and_reels_are_independent_across_engines(tmp_path: Path) -> None:
    def handle(spec: CommandSpec) -> CommandResult:
        engine, _, url = spec.argv
        if engine == "gallery-dl" and url.endswith("/example/"):
            return command_result(1, "unsupported URL")
        return command_result(0, "downloaded=1")

    runner = FakeRunner(handler=handle)
    gallery = FakeEngine("gallery-dl")
    alternate = FakeEngine("yt-dlp")
    service = service_with(runner, (gallery, alternate))

    batch = service.execute(request_for(tmp_path, media=(MediaKind.VIDEOS,))[0])

    assert len(batch.results) == 2
    assert [result.outcome for result in batch.results] == [
        Outcome.DOWNLOADED,
        Outcome.DOWNLOADED,
    ]
    assert [len(result.attempts) for result in batch.results] == [2, 1]
    assert [spec.argv[2] for spec in runner.calls] == [
        "https://www.instagram.com/example/",
        "https://www.instagram.com/example/",
        "https://www.instagram.com/example/reels/",
    ]


def test_archive_lock_contention_blocks_operation_without_running(tmp_path: Path) -> None:
    request, _ = request_for(tmp_path)
    step = build_plan(request)[0]
    lock = ArchiveLock(step.destination / "archive.txt", timeout=0)
    _ = lock.acquire()
    try:
        runner = FakeRunner([])
        result = service_with(runner, (FakeEngine("gallery-dl"),)).execute(request).results[0]
    finally:
        lock.release()

    assert result.outcome is Outcome.FAILED
    assert result.failure_kind is FailureKind.LOCKED
    assert runner.calls == []


def test_execution_never_changes_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = FakeRunner([command_result(0)])
    engine = FakeEngine("gallery-dl")
    original = Path.cwd()

    def forbid_chdir(path: object) -> None:
        raise AssertionError(f"unexpected chdir: {path}")

    monkeypatch.setattr(os, "chdir", forbid_chdir)
    result = service_with(runner, (engine,)).execute(request_for(tmp_path)[0])

    assert result.results[0].outcome is Outcome.UP_TO_DATE
    assert Path.cwd() == original
