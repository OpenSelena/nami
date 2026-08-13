"""Platform adapters for Nami."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from nami.auth import AuthConfig
from nami.parser import ParsedTarget
from nami.retry import FailureType


class DownloadResultStatus(Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


@dataclass
class DownloadResult:
    status: DownloadResultStatus
    extractor: str | None = None
    fallback_extractor: str | None = None
    failure_type: FailureType | None = None
    items_discovered: int = 0
    items_downloaded: int = 0
    items_skipped: int = 0
    message: str = ""

    def to_display_string(self) -> str:
        if self.status == DownloadResultStatus.SUCCESS:
            if self.fallback_extractor:
                return f"✓ ({self.fallback_extractor})"
            elif self.extractor:
                return f"✓ ({self.extractor})"
            return "✓"
        elif self.status == DownloadResultStatus.UNSUPPORTED:
            return "N/A"
        elif self.status == DownloadResultStatus.SKIPPED:
            return "-"
        else:
            reason = self.failure_type.value if self.failure_type else "failed"
            return f"✗ ({reason})"


class BasePlatformAdapter(ABC):
    @property
    @abstractmethod
    def platform_name(self) -> str:
        pass

    @abstractmethod
    def download_photos(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        pass

    @abstractmethod
    def download_videos(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        pass

    @abstractmethod
    def download_stories(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        pass

    @abstractmethod
    def download_highlights(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        pass
