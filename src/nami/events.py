"""Framework-agnostic events emitted while downloads execute."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias

JsonValue: TypeAlias = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None


@dataclass(frozen=True, slots=True)
class DownloadEvent:
    """A JSON-serializable event produced by the execution layer."""

    kind: str
    message: str
    data: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("event kind must not be empty")
        copied = dict(self.data)
        try:
            _ = json.dumps(copied, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("event data must be JSON-safe") from error
        object.__setattr__(self, "data", copied)


class EventSink(Protocol):
    """Receives execution events synchronously."""

    def emit(self, event: DownloadEvent) -> None:
        """Handle one event."""


@dataclass(frozen=True, slots=True)
class NullEventSink:
    """An event sink that intentionally discards every event."""

    def emit(self, event: DownloadEvent) -> None:
        del event


@dataclass(frozen=True, slots=True)
class CallbackEventSink:
    """Adapt a callback to the :class:`EventSink` protocol."""

    callback: Callable[[DownloadEvent], None]

    def emit(self, event: DownloadEvent) -> None:
        self.callback(event)
