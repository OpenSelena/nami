"""gallery-dl extractor engine for Nami."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nami.archive import ArchiveLock, init_archive_dir
from nami.auth import AuthConfig
from nami.config import PHOTO_FILTER, VIDEO_FILTER
from nami.downloader import download_gd
from nami.extractors.base import BaseExtractor
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.retry import execute_with_intelligent_retry

SUPPORTED_TYPES = {
    "instagram": {"profile", "post", "reel", "story", "highlight"},
    "tiktok": {"profile", "post", "video"},
    "facebook": {"profile", "post", "video"},
    "x": {"profile", "post", "video"},
}


class GalleryDlExtractor(BaseExtractor):
    name = "gallery-dl"

    def supports(self, platform: str, content_type: str) -> bool:
        plat = platform.lower()
        types = SUPPORTED_TYPES.get(plat, set())
        return content_type in types or content_type in ("photos", "videos")

    def download(
        self,
        target: ParsedTarget,
        destination: Path,
        auth: AuthConfig,
        progress_obj: Any = None,
        active_task_id: Any = None,
        context: dict[str, Any] | None = None,
    ) -> DownloadResult:
        destination.mkdir(parents=True, exist_ok=True)
        init_archive_dir(destination)
        cookies_arg = auth.to_cli_args()
        log_file = destination / "lastrun.log"

        filter_str = None
        if context and "filter" in context:
            filter_str = context["filter"]
        elif target.content_type in ("photos", "photo"):
            filter_str = PHOTO_FILTER
        elif target.content_type in ("videos", "video"):
            filter_str = VIDEO_FILTER

        target_url = (context and context.get("url")) or target.original_url

        def attempt(cookies: list[str], silent: bool) -> tuple[int, str, str]:
            sleep_time = "1" if silent else "5"
            return download_gd(
                destination, filter_str, cookies, target_url,
                sleep_time=sleep_time, silent=silent,
                progress_obj=progress_obj, active_task_id=active_task_id
            )

        with ArchiveLock(destination):
            rc, failure_type, output = execute_with_intelligent_retry(
                attempt, cookies_arg, log_file, f"gallery-dl ({target.platform})"
            )

        if rc == 0:
            return DownloadResult(
                status=DownloadResultStatus.SUCCESS,
                extractor=self.name,
                message=output[:200]
            )

        return DownloadResult(
            status=DownloadResultStatus.FAILED,
            extractor=self.name,
            failure_type=failure_type,
            message=output[:200]
        )
