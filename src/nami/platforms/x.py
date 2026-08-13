"""X / Twitter platform adapter for Nami."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nami.auth import AuthConfig
from nami.extractor_manager import ExtractorManager
from nami.parser import ParsedTarget
from nami.platforms import BasePlatformAdapter, DownloadResult, DownloadResultStatus


class XAdapter(BasePlatformAdapter):
    def __init__(self, manager: ExtractorManager | None = None) -> None:
        self.manager = manager or ExtractorManager()

    @property
    def platform_name(self) -> str:
        return "x"

    def download_photos(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        photos_dir = target_dir / "Photos"
        return self.manager.download(
            target=target,
            content_type="photos",
            destination=photos_dir,
            auth=auth_config,
            progress_obj=progress_obj,
            active_task_id=active_task_id,
        )

    def download_videos(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        videos_dir = target_dir / "Videos"
        return self.manager.download(
            target=target,
            content_type="videos",
            destination=videos_dir,
            auth=auth_config,
            progress_obj=progress_obj,
            active_task_id=active_task_id,
        )

    def download_stories(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        return DownloadResult(status=DownloadResultStatus.UNSUPPORTED, message="Stories not supported for X/Twitter")

    def download_highlights(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        return DownloadResult(status=DownloadResultStatus.UNSUPPORTED, message="Highlights not supported for X/Twitter")
