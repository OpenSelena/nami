"""yt-dlp extractor engine for Nami."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nami.archive import ArchiveLock, init_archive_dir
from nami.auth import AuthConfig
from nami.downloader import download_yt
from nami.extractors.base import BaseExtractor
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.retry import execute_with_intelligent_retry

SUPPORTED_TYPES = {
    "instagram": {"post", "reel", "video"},
    "tiktok": {"profile", "video"},
    "facebook": {"video"},
    "x": {"video"},
}


class YtDlpExtractor(BaseExtractor):
    name = "yt-dlp"

    def supports(self, platform: str, content_type: str) -> bool:
        plat = platform.lower()
        types = SUPPORTED_TYPES.get(plat, set())
        return content_type in types or content_type in ("videos", "video")

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

        target_url = (context and context.get("url")) or target.original_url

        def attempt(cookies: list[str], silent: bool) -> tuple[int, str, str]:
            return download_yt(
                destination, cookies, target_url, silent=silent,
                progress_obj=progress_obj, active_task_id=active_task_id
            )

        with ArchiveLock(destination):
            rc, failure_type, output = execute_with_intelligent_retry(
                attempt, cookies_arg, log_file, f"yt-dlp ({target.platform})"
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
