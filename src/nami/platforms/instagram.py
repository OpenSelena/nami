"""Instagram platform adapter for Nami."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nami.archive import init_archive_dir, ArchiveLock
from nami.auth import AuthConfig
from nami.config import PHOTO_FILTER, VIDEO_FILTER
from nami.downloader import download_gd, download_yt
from nami.parser import ParsedTarget
from nami.platforms import BasePlatformAdapter, DownloadResult, DownloadResultStatus
from nami.retry import execute_with_intelligent_retry, FailureType


class InstagramAdapter(BasePlatformAdapter):
    @property
    def platform_name(self) -> str:
        return "instagram"

    def download_photos(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        photos_dir = target_dir / "Photos"
        init_archive_dir(photos_dir)
        cookies_arg = auth_config.to_cli_args()
        log_file = photos_dir / "lastrun.log"

        def attempt(cookies: list[str], silent: bool) -> tuple[int, str, str]:
            sleep_time = "1" if silent else "5"
            return download_gd(
                photos_dir, PHOTO_FILTER, cookies, target.original_url,
                sleep_time=sleep_time, silent=silent,
                progress_obj=progress_obj, active_task_id=active_task_id
            )

        with ArchiveLock(photos_dir):
            rc, failure_type, output = execute_with_intelligent_retry(
                attempt, cookies_arg, log_file, "gallery-dl (instagram photos)"
            )

        if rc == 0:
            return DownloadResult(status=DownloadResultStatus.SUCCESS)
        return DownloadResult(status=DownloadResultStatus.FAILED, failure_type=failure_type, message=output[:200])

    def download_videos(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        videos_dir = target_dir / "Videos"
        init_archive_dir(videos_dir)
        cookies_arg = auth_config.to_cli_args()
        log_file = videos_dir / "lastrun.log"

        def attempt_gd(cookies: list[str], silent: bool) -> tuple[int, str, str]:
            return download_gd(
                videos_dir, VIDEO_FILTER, cookies, target.original_url,
                sleep_time="1" if silent else "5", silent=silent,
                progress_obj=progress_obj, active_task_id=active_task_id
            )

        with ArchiveLock(videos_dir):
            rc, failure_type, output = execute_with_intelligent_retry(
                attempt_gd, cookies_arg, log_file, "gallery-dl (instagram videos)"
            )

            # Check Reels URL if username is present
            if target.username:
                reels_url = f"https://www.instagram.com/{target.username}/reels/"
                def attempt_reels(cookies: list[str], silent: bool) -> tuple[int, str, str]:
                    return download_gd(
                        videos_dir, VIDEO_FILTER, cookies, reels_url,
                        sleep_time="1" if silent else "5", silent=silent,
                        progress_obj=progress_obj, active_task_id=active_task_id
                    )
                r_rc, r_failure, _ = execute_with_intelligent_retry(
                    attempt_reels, cookies_arg, log_file, "gallery-dl (instagram reels)"
                )
                if r_rc != 0 and rc == 0:
                    rc = r_rc
                    failure_type = r_failure

            if rc != 0:
                def attempt_yt(cookies: list[str], silent: bool) -> tuple[int, str, str]:
                    return download_yt(
                        videos_dir, cookies, target.original_url, silent=silent,
                        progress_obj=progress_obj, active_task_id=active_task_id
                    )
                yt_rc, yt_failure, yt_output = execute_with_intelligent_retry(
                    attempt_yt, cookies_arg, log_file, "yt-dlp (instagram videos)"
                )
                rc = yt_rc
                failure_type = yt_failure
                output = yt_output

        if rc == 0:
            return DownloadResult(status=DownloadResultStatus.SUCCESS)
        return DownloadResult(status=DownloadResultStatus.FAILED, failure_type=failure_type, message=output[:200])

    def download_stories(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        if not target.username:
            return DownloadResult(status=DownloadResultStatus.FAILED, failure_type=FailureType.NOT_FOUND, message="No username for stories")

        stories_dir = target_dir / "Stories"
        init_archive_dir(stories_dir)
        cookies_arg = auth_config.to_cli_args()
        log_file = stories_dir / "lastrun.log"
        stories_url = f"https://www.instagram.com/stories/{target.username}/"

        def attempt(cookies: list[str], silent: bool) -> tuple[int, str, str]:
            return download_gd(
                stories_dir, None, cookies, stories_url,
                sleep_time="1" if silent else "5", silent=silent,
                progress_obj=progress_obj, active_task_id=active_task_id
            )

        with ArchiveLock(stories_dir):
            rc, failure_type, output = execute_with_intelligent_retry(
                attempt, cookies_arg, log_file, "gallery-dl (instagram stories)"
            )

        if rc == 0:
            return DownloadResult(status=DownloadResultStatus.SUCCESS)
        return DownloadResult(status=DownloadResultStatus.FAILED, failure_type=failure_type, message=output[:200])

    def download_highlights(
        self,
        target_dir: Path,
        auth_config: AuthConfig,
        target: ParsedTarget,
        progress_obj: Any = None,
        active_task_id: Any = None,
    ) -> DownloadResult:
        if not target.username:
            return DownloadResult(status=DownloadResultStatus.FAILED, failure_type=FailureType.NOT_FOUND, message="No username for highlights")

        hl_dir = target_dir / "Highlights"
        init_archive_dir(hl_dir)
        cookies_arg = auth_config.to_cli_args()
        log_file = hl_dir / "lastrun.log"
        hl_url = f"https://www.instagram.com/{target.username}/highlights/"

        def attempt(cookies: list[str], silent: bool) -> tuple[int, str, str]:
            return download_gd(
                hl_dir, None, cookies, hl_url,
                sleep_time="1" if silent else "5", silent=silent,
                progress_obj=progress_obj, active_task_id=active_task_id
            )

        with ArchiveLock(hl_dir):
            rc, failure_type, output = execute_with_intelligent_retry(
                attempt, cookies_arg, log_file, "gallery-dl (instagram highlights)"
            )

        if rc == 0:
            return DownloadResult(status=DownloadResultStatus.SUCCESS)
        return DownloadResult(status=DownloadResultStatus.FAILED, failure_type=failure_type, message=output[:200])
