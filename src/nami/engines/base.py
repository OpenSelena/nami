"""Shared interfaces for downloader command adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Protocol, runtime_checkable

from nami.auth import AuthSpec
from nami.models import MediaKind, Target
from nami.process import CommandSpec


@dataclass(frozen=True, slots=True)
class EngineRequest:
    """All inputs required to construct one downloader invocation."""

    target: Target
    media: MediaKind
    destination: Path
    url: str
    auth: AuthSpec
    archive: Path
    user_agent: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("url must not be empty")
        if not self.user_agent:
            raise ValueError("user_agent must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        object.__setattr__(self, "destination", Path(self.destination))
        object.__setattr__(self, "archive", Path(self.archive))


class EngineAnalysis(NamedTuple):
    """Conservative counts inferred from downloader output."""

    downloaded: int
    archived: int


@runtime_checkable
class Engine(Protocol):
    """Build and interpret commands for a downloader backend."""

    name: str

    def supports(self, target: Target, media: MediaKind) -> bool:
        """Return whether this backend supports the target/media combination."""
        ...

    def build_command(self, request: EngineRequest) -> CommandSpec:
        """Build a shell-free command specification."""
        ...

    def analyze_output(self, lines: Iterable[str]) -> EngineAnalysis:
        """Count downloaded and archive-skipped items in output lines."""
        ...
