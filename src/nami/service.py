"""Download orchestration built on Nami's side-effect boundaries."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from nami.archive import ArchiveBusyError, ArchiveLock, archive_path
from nami.auth import AuthMode, AuthSpec, resolve_auth
from nami.config import Settings
from nami.engines import Engine, EngineRequest, GalleryDlEngine, YtDlpEngine
from nami.events import DownloadEvent, EventSink, NullEventSink
from nami.failures import classify_failure
from nami.models import (
    AttemptResult,
    BatchResult,
    FailureKind,
    OperationResult,
    Outcome,
    Platform,
    Target,
)
from nami.planner import DownloadRequest, PlanStep, build_plan
from nami.process import CommandResult, CommandSpec, SubprocessRunner
from nami.retry import RetryDecision, RetryPolicy
from nami.targets import safe_target_dir

Sleeper = Callable[[float], None]
AuthResolver = Callable[[Platform | str, Settings], AuthSpec]


class Runner(Protocol):
    def run(
        self,
        spec: CommandSpec,
        *,
        event_sink: EventSink | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CommandResult:
        """Execute one command and return its captured result."""
        ...


class NamiService:
    """Plan and execute downloads using injected engines and process services."""

    def __init__(
        self,
        *,
        engines: Mapping[str, Engine] | None = None,
        runner: Runner | None = None,
        policy: RetryPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper: Sleeper | None = None,
        event_sink: EventSink | None = None,
        sink: EventSink | None = None,
        auth_resolver: AuthResolver = resolve_auth,
        lock_timeout: float = 0.0,
    ) -> None:
        if policy is not None and retry_policy is not None:
            raise TypeError("provide policy or retry_policy, not both")
        if event_sink is not None and sink is not None:
            raise TypeError("provide event_sink or sink, not both")
        if lock_timeout < 0:
            raise ValueError("lock_timeout must not be negative")

        if engines is None:
            defaults: tuple[Engine, ...] = (GalleryDlEngine(), YtDlpEngine())
            engines = {engine.name: engine for engine in defaults}
        self.engines: dict[str, Engine] = dict(engines)
        self.runner: Runner = runner if runner is not None else SubprocessRunner()
        self.policy: RetryPolicy = policy or retry_policy or RetryPolicy()
        self.sleeper: Sleeper = sleeper or time.sleep
        self.event_sink: EventSink = event_sink or sink or NullEventSink()
        self.auth_resolver: AuthResolver = auth_resolver
        self.lock_timeout: float = lock_timeout

    @classmethod
    def default(
        cls,
        *,
        event_sink: EventSink | None = None,
        policy: RetryPolicy | None = None,
    ) -> NamiService:
        """Create a service backed by the bundled engines and subprocess runner."""

        return cls(event_sink=event_sink, policy=policy)

    def execute(
        self,
        request: DownloadRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BatchResult:
        """Build and execute every plan step in deterministic order."""

        plan = build_plan(request)
        auth_by_target: dict[Target, AuthSpec] = {}
        results: list[OperationResult] = []
        for step in plan:
            if step.target not in auth_by_target:
                auth_by_target[step.target] = self.auth_resolver(step.target.platform, request.settings)
            result = self._execute_step(
                step,
                request.settings,
                auth_by_target[step.target],
                cancel_event,
            )
            results.append(result)
            if result.outcome is Outcome.CANCELLED:
                break
        return BatchResult(tuple(results))

    def run(
        self,
        request: DownloadRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BatchResult:
        """Compatibility alias for :meth:`execute`."""

        return self.execute(request, cancel_event=cancel_event)

    def download(
        self,
        request: DownloadRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BatchResult:
        """Compatibility alias for :meth:`execute`."""

        return self.execute(request, cancel_event=cancel_event)

    def _execute_step(
        self,
        step: PlanStep,
        settings: Settings,
        initial_auth: AuthSpec,
        cancel_event: threading.Event | None,
    ) -> OperationResult:
        if not step.supported:
            result = OperationResult(
                target=step.target,
                media_kind=step.media,
                outcome=Outcome.UNSUPPORTED,
                message=step.reason or "This operation is not supported",
            )
            self._emit_result(step, result)
            return result

        if cancel_event is not None and cancel_event.is_set():
            result = OperationResult(
                target=step.target,
                media_kind=step.media,
                outcome=Outcome.CANCELLED,
                message="Download cancelled before the operation started",
            )
            self._emit_result(step, result)
            return result

        try:
            destination = self._safe_destination(step, settings)
            destination.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            result = OperationResult(
                target=step.target,
                media_kind=step.media,
                outcome=Outcome.FAILED,
                failure_kind=FailureKind.CONFIG,
                message=f"Could not prepare destination: {exc}",
            )
            self._emit_result(step, result)
            return result

        archive = archive_path(destination)
        lock = ArchiveLock(archive, timeout=self.lock_timeout)
        try:
            _ = lock.acquire()
        except ArchiveBusyError:
            result = OperationResult(
                target=step.target,
                media_kind=step.media,
                outcome=Outcome.FAILED,
                failure_kind=FailureKind.LOCKED,
                message=f"Archive is in use for {step.label}",
            )
            self._emit_result(step, result)
            return result
        except OSError as exc:
            result = OperationResult(
                target=step.target,
                media_kind=step.media,
                outcome=Outcome.FAILED,
                failure_kind=FailureKind.LOCKED,
                message=f"Could not acquire archive lock: {exc}",
            )
            self._emit_result(step, result)
            return result

        try:
            result = self._run_locked(
                step,
                settings,
                destination,
                archive,
                initial_auth,
                cancel_event,
            )
        finally:
            lock.release()
        self._emit_result(step, result)
        return result

    def _run_locked(
        self,
        step: PlanStep,
        settings: Settings,
        destination: Path,
        archive: Path,
        initial_auth: AuthSpec,
        cancel_event: threading.Event | None,
    ) -> OperationResult:
        attempts: list[AttemptResult] = []
        engine_index = 0
        engine_attempt = 0
        current_auth = initial_auth
        anonymous_retry_used = False
        auth_fallback_started = False

        while engine_index < len(step.engines):
            engine_name = step.engines[engine_index]
            engine = self.engines.get(engine_name)
            if engine is None:
                attempt = AttemptResult(
                    outcome=Outcome.FAILED,
                    extractor=engine_name,
                    failure_kind=FailureKind.DEPENDENCY,
                    message=f"Downloader engine is unavailable: {engine_name}",
                )
                attempts.append(attempt)
                return self._failed_operation(step, attempts, attempt)
            if not engine.supports(step.target, step.media):
                attempt = AttemptResult(
                    outcome=Outcome.FAILED,
                    extractor=engine_name,
                    failure_kind=FailureKind.EXTRACTOR,
                    message=f"{engine_name} does not support {step.label}",
                )
                attempts.append(attempt)
                alternate_index = self._alternate_index(step, engine_index)
                decision = self._constrain_decision(
                    FailureKind.EXTRACTOR,
                    self.policy.decide(
                        FailureKind.EXTRACTOR,
                        attempt=1,
                        alternate_available=alternate_index is not None,
                    ),
                    current_auth,
                    anonymous_retry_used,
                )
                if not decision.use_alternate_engine or alternate_index is None:
                    return self._failed_operation(step, attempts, attempt)
                engine_index = alternate_index
                engine_attempt = 0
                self._emit_retry(
                    step,
                    engine_name,
                    FailureKind.EXTRACTOR,
                    decision,
                    step.engines[engine_index],
                )
                continue

            if cancel_event is not None and cancel_event.is_set():
                attempt = AttemptResult(
                    outcome=Outcome.CANCELLED,
                    extractor=engine_name,
                    message="Download cancelled",
                )
                attempts.append(attempt)
                return self._cancelled_operation(step, attempts)

            engine_attempt += 1
            self._emit_start(step, engine_name, len(attempts) + 1, engine_attempt, current_auth)
            engine_request = EngineRequest(
                target=step.target,
                media=step.media,
                destination=destination,
                url=step.url,
                auth=current_auth,
                archive=archive,
                user_agent=settings.user_agent,
                timeout_seconds=settings.timeout_seconds,
            )

            try:
                command = engine.build_command(engine_request)
                command_result = self._run_command(command, cancel_event)
            except KeyboardInterrupt:
                attempt = AttemptResult(
                    outcome=Outcome.CANCELLED,
                    extractor=engine_name,
                    message="Download cancelled",
                )
                attempts.append(attempt)
                return self._cancelled_operation(step, attempts)
            except OSError as exc:
                attempt = AttemptResult(
                    outcome=Outcome.FAILED,
                    extractor=engine_name,
                    failure_kind=FailureKind.DEPENDENCY,
                    message=f"Could not start {engine_name}: {exc}",
                )
                attempts.append(attempt)
                return self._failed_operation(step, attempts, attempt)
            except (TypeError, ValueError, RuntimeError) as exc:
                attempt = AttemptResult(
                    outcome=Outcome.FAILED,
                    extractor=engine_name,
                    failure_kind=FailureKind.UNKNOWN,
                    message=f"{engine_name} could not execute safely: {exc}",
                )
                attempts.append(attempt)
                return self._failed_operation(step, attempts, attempt)

            terminal = self._interpret_result(engine, engine_name, command_result)
            attempts.append(terminal)
            if terminal.outcome is Outcome.CANCELLED:
                return self._cancelled_operation(step, attempts)
            if terminal.outcome in {Outcome.DOWNLOADED, Outcome.UP_TO_DATE}:
                return OperationResult(
                    target=step.target,
                    media_kind=step.media,
                    outcome=terminal.outcome,
                    attempts=tuple(attempts),
                    message=terminal.message,
                    downloaded_count=terminal.downloaded_count,
                    existing_count=terminal.existing_count,
                )
            if terminal.outcome is Outcome.NO_RESULTS:
                return OperationResult(
                    target=step.target,
                    media_kind=step.media,
                    outcome=Outcome.NO_RESULTS,
                    attempts=tuple(attempts),
                    failure_kind=FailureKind.NOT_FOUND,
                    message=terminal.message,
                )

            failure = terminal.failure_kind or FailureKind.UNKNOWN
            alternate_index = self._alternate_index(step, engine_index)
            if auth_fallback_started:
                decision = RetryDecision(
                    retry=False,
                    reason="anonymous authentication fallback already completed",
                )
            else:
                decision = self.policy.decide(
                    failure,
                    attempt=engine_attempt,
                    auth_supplied=current_auth.mode is not AuthMode.NONE,
                    anonymous_retry_used=anonymous_retry_used,
                    alternate_available=alternate_index is not None,
                )

            decision = self._constrain_decision(
                failure,
                decision,
                current_auth,
                anonymous_retry_used,
            )
            if not decision.retry:
                return self._failed_operation(step, attempts, terminal)

            if decision.use_anonymous:
                anonymous_retry_used = True
                auth_fallback_started = True
                current_auth = AuthSpec(AuthMode.NONE)
            elif decision.use_alternate_engine:
                if alternate_index is None:
                    return self._failed_operation(step, attempts, terminal)
                engine_index = alternate_index
                engine_attempt = 0
            elif not decision.retry_same_engine:
                return self._failed_operation(step, attempts, terminal)

            self._emit_retry(
                step,
                engine_name,
                failure,
                decision,
                step.engines[engine_index],
            )
            if decision.delay_seconds > 0:
                self.sleeper(decision.delay_seconds)

        last = (
            attempts[-1]
            if attempts
            else AttemptResult(
                outcome=Outcome.FAILED,
                failure_kind=FailureKind.DEPENDENCY,
                message="No downloader engine was available",
            )
        )
        return self._failed_operation(step, attempts, last)

    def _run_command(self, command: CommandSpec, cancel_event: threading.Event | None) -> CommandResult:
        return self.runner.run(
            command,
            event_sink=self.event_sink,
            cancel_event=cancel_event,
        )

    @staticmethod
    def _interpret_result(engine: Engine, engine_name: str, result: CommandResult) -> AttemptResult:
        if result.cancelled:
            return AttemptResult(
                outcome=Outcome.CANCELLED,
                extractor=engine_name,
                message="Download cancelled",
                return_code=result.returncode,
            )

        failure = classify_failure(result)
        if failure is None:
            analysis = engine.analyze_output(result.lines)
            if analysis.downloaded > 0:
                return AttemptResult(
                    outcome=Outcome.DOWNLOADED,
                    extractor=engine_name,
                    message=f"Downloaded {analysis.downloaded} file(s)",
                    return_code=result.returncode,
                    downloaded_count=analysis.downloaded,
                    existing_count=analysis.archived,
                )
            return AttemptResult(
                outcome=Outcome.UP_TO_DATE,
                extractor=engine_name,
                message=(
                    f"No new files; {analysis.archived} item(s) already archived"
                    if analysis.archived
                    else "No new files were emitted"
                ),
                return_code=result.returncode,
                existing_count=analysis.archived,
            )

        if failure is FailureKind.NOT_FOUND:
            return AttemptResult(
                outcome=Outcome.NO_RESULTS,
                extractor=engine_name,
                failure_kind=failure,
                message="No matching content was found",
                return_code=result.returncode,
            )
        return AttemptResult(
            outcome=Outcome.FAILED,
            extractor=engine_name,
            failure_kind=failure,
            message=_failure_message(failure),
            return_code=result.returncode,
        )

    def _alternate_index(self, step: PlanStep, current: int) -> int | None:
        for index in range(current + 1, len(step.engines)):
            engine = self.engines.get(step.engines[index])
            if engine is not None and engine.supports(step.target, step.media):
                return index
        return None

    @staticmethod
    def _constrain_decision(
        failure: FailureKind,
        decision: RetryDecision,
        auth: AuthSpec,
        anonymous_retry_used: bool,
    ) -> RetryDecision:
        if not decision.retry:
            return decision
        if failure in {FailureKind.AUTH, FailureKind.COOKIE}:
            allowed = decision.use_anonymous and auth.mode is not AuthMode.NONE and not anonymous_retry_used
        elif failure in {FailureKind.NETWORK, FailureKind.TIMEOUT}:
            allowed = decision.retry_same_engine
        elif failure is FailureKind.EXTRACTOR:
            allowed = decision.use_alternate_engine
        else:
            allowed = False
        if allowed:
            return decision
        return RetryDecision(
            retry=False,
            reason=f"unsafe retry action rejected for {failure.value} failure",
        )

    @staticmethod
    def _safe_destination(step: PlanStep, settings: Settings) -> Path:
        target_root = safe_target_dir(settings.base_dir, step.target)
        destination = step.destination.expanduser().resolve()
        _ = destination.relative_to(target_root)
        return destination

    @staticmethod
    def _failed_operation(
        step: PlanStep,
        attempts: list[AttemptResult],
        final: AttemptResult,
    ) -> OperationResult:
        return OperationResult(
            target=step.target,
            media_kind=step.media,
            outcome=Outcome.FAILED,
            attempts=tuple(attempts),
            failure_kind=final.failure_kind or FailureKind.UNKNOWN,
            message=final.message or "Download failed",
        )

    @staticmethod
    def _cancelled_operation(step: PlanStep, attempts: list[AttemptResult]) -> OperationResult:
        return OperationResult(
            target=step.target,
            media_kind=step.media,
            outcome=Outcome.CANCELLED,
            attempts=tuple(attempts),
            message="Download cancelled",
        )

    def _emit_start(
        self,
        step: PlanStep,
        engine_name: str,
        attempt: int,
        engine_attempt: int,
        auth: AuthSpec,
    ) -> None:
        self.event_sink.emit(
            DownloadEvent(
                "start",
                f"Starting {step.label} with {engine_name}",
                {
                    "label": step.label,
                    "platform": step.target.platform.value,
                    "target": step.target.target_key,
                    "media": step.media.value,
                    "engine": engine_name,
                    "attempt": attempt,
                    "engine_attempt": engine_attempt,
                    "auth_mode": auth.mode.value,
                },
            )
        )

    def _emit_retry(
        self,
        step: PlanStep,
        engine_name: str,
        failure: FailureKind,
        decision: RetryDecision,
        next_engine: str,
    ) -> None:
        self.event_sink.emit(
            DownloadEvent(
                "retry",
                decision.reason or f"Retrying {step.label}",
                {
                    "label": step.label,
                    "engine": engine_name,
                    "next_engine": next_engine,
                    "failure_kind": failure.value,
                    "delay_seconds": decision.delay_seconds,
                    "anonymous": decision.use_anonymous,
                },
            )
        )

    def _emit_result(self, step: PlanStep, result: OperationResult) -> None:
        self.event_sink.emit(
            DownloadEvent(
                "result",
                result.message or f"{step.label}: {result.outcome.value}",
                {
                    "label": step.label,
                    "outcome": result.outcome.value,
                    "failure_kind": (result.failure_kind.value if result.failure_kind else None),
                    "downloaded_count": result.downloaded_count,
                    "existing_count": result.existing_count,
                },
            )
        )


def create_default_service(*, event_sink: EventSink | None = None) -> NamiService:
    """Return the production service with bundled downloader adapters."""

    return NamiService.default(event_sink=event_sink)


def _failure_message(failure: FailureKind) -> str:
    messages = {
        FailureKind.AUTH: "Authentication was rejected",
        FailureKind.COOKIE: "Cookies could not be loaded",
        FailureKind.RATE_LIMIT: "The platform rate limit was reached",
        FailureKind.NETWORK: "A network error interrupted the download",
        FailureKind.EXTRACTOR: "The downloader could not extract this URL",
        FailureKind.NOT_FOUND: "No matching content was found",
        FailureKind.DEPENDENCY: "A downloader dependency is unavailable",
        FailureKind.TIMEOUT: "The downloader timed out",
        FailureKind.LOCKED: "The account or archive is locked",
        FailureKind.CONFIG: "The download configuration is invalid",
        FailureKind.UNKNOWN: "The downloader failed for an unknown reason",
    }
    return messages[failure]
