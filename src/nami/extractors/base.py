"""Base extractor interface for Nami."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from nami.auth import AuthConfig
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult


class BaseExtractor(ABC):
    name: str

    @abstractmethod
    def supports(self, platform: str, content_type: str) -> bool:
        """Check if this extractor supports given platform and content_type."""
        pass

    @abstractmethod
    def download(
        self,
        target: ParsedTarget,
        destination: Path,
        auth: AuthConfig,
        progress_obj: Any = None,
        active_task_id: Any = None,
        context: dict[str, Any] | None = None,
    ) -> DownloadResult:
        """Execute download operation and return structured DownloadResult."""
        pass
