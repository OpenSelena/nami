"""Immutable domain models shared by Nami's foundation layer."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    X = "x"


class MediaKind(str, Enum):
    PHOTOS = "photos"
    VIDEOS = "videos"
    STORIES = "stories"
    HIGHLIGHTS = "highlights"


class Outcome(str, Enum):
    DOWNLOADED = "downloaded"
    UP_TO_DATE = "up_to_date"
    NO_RESULTS = "no_results"
    UNSUPPORTED = "unsupported"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INVALID = "invalid"


class FailureKind(str, Enum):
    AUTH = "auth"
    COOKIE = "cookie"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    EXTRACTOR = "extractor"
    NOT_FOUND = "not_found"
    DEPENDENCY = "dependency"
    TIMEOUT = "timeout"
    LOCKED = "locked"
    CONFIG = "config"
    UNKNOWN = "unknown"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_safe(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class _JsonModel:
    def to_dict(self) -> dict[str, Any]:
        """Return a recursively JSON-serializable representation."""
        return _json_safe(self)


@dataclass(frozen=True)
class Target(_JsonModel):
    original_url: str
    canonical_url: str
    target_key: str
    platform: Platform
    username: str | None
    content_type: str
    content_id: str | None = None


@dataclass(frozen=True)
class AttemptResult(_JsonModel):
    outcome: Outcome
    extractor: str | None = None
    failure_kind: FailureKind | None = None
    message: str | None = None
    return_code: int | None = None
    downloaded_count: int = 0
    existing_count: int = 0


@dataclass(frozen=True)
class OperationResult(_JsonModel):
    target: Target
    media_kind: MediaKind
    outcome: Outcome
    attempts: tuple[AttemptResult, ...] = ()
    failure_kind: FailureKind | None = None
    message: str | None = None
    downloaded_count: int = 0
    existing_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", tuple(self.attempts))


@dataclass(frozen=True, init=False)
class BatchResult(_JsonModel):
    results: tuple[OperationResult, ...] = ()

    def __init__(
        self,
        results: tuple[OperationResult, ...] = (),
        *,
        operations: tuple[OperationResult, ...] | None = None,
    ) -> None:
        if operations is not None:
            if results:
                raise TypeError("provide results or operations, not both")
            results = operations
        object.__setattr__(self, "results", tuple(results))

    @property
    def operations(self) -> tuple[OperationResult, ...]:
        """Compatibility alias for callers that describe results as operations."""
        return self.results

    def exit_code(self) -> int:
        """Map aggregate outcomes to Nami's deterministic process exit codes."""
        if not self.results:
            return 0

        outcomes = tuple(result.outcome for result in self.results)
        if Outcome.CANCELLED in outcomes:
            return 130
        if Outcome.INVALID in outcomes or any(result.failure_kind is FailureKind.CONFIG for result in self.results):
            return 2

        successful = {Outcome.DOWNLOADED, Outcome.UP_TO_DATE}
        if all(outcome in successful for outcome in outcomes):
            return 0
        if all(outcome is Outcome.FAILED for outcome in outcomes):
            return 1
        if all(outcome is Outcome.NO_RESULTS for outcome in outcomes):
            return 4

        # PARTIAL, unsupported-only, and every mixture involving an operational
        # failure intentionally share the same actionable exit status.
        return 3
