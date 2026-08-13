"""Instaloader Python-native extractor engine for Nami."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nami.archive import ArchiveLock, init_archive_dir
from nami.auth import AuthConfig
from nami.extractors.base import BaseExtractor
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.retry import FailureType

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {"profile", "post", "reel", "story", "highlight", "photos", "videos"}


class InstaloaderExtractor(BaseExtractor):
    name = "instaloader"

    def supports(self, platform: str, content_type: str) -> bool:
        if platform.lower() != "instagram":
            return False
        return content_type in SUPPORTED_TYPES

    def _init_instaloader(self, destination: Path, auth: AuthConfig) -> Any:
        import instaloader

        L = instaloader.Instaloader(
            dirname_pattern=str(destination),
            filename_pattern="{date_utc}_UTC",
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )

        if auth.mode == "instaloader_session" and auth.path and auth.path.exists():
            try:
                username = auth.username or "user"
                L.load_session_from_file(username, str(auth.path))
            except Exception as e:
                logger.warning(f"Could not load Instaloader session file {auth.path}: {e}")

        return L

    def download(
        self,
        target: ParsedTarget,
        destination: Path,
        auth: AuthConfig,
        progress_obj: Any = None,
        active_task_id: Any = None,
        context: dict[str, Any] | None = None,
    ) -> DownloadResult:
        if target.platform.lower() != "instagram":
            return DownloadResult(
                status=DownloadResultStatus.UNSUPPORTED,
                extractor=self.name,
                failure_type=FailureType.EXTRACTOR,
                message="Instaloader is only supported for Instagram",
            )

        destination.mkdir(parents=True, exist_ok=True)
        init_archive_dir(destination)

        with ArchiveLock(destination):
            try:
                import instaloader
                from instaloader.exceptions import (
                    BadCredentialsException,
                    ConnectionException,
                    InvalidArgumentException,
                    LoginException,
                    LoginRequiredException,
                    PrivateProfileNotFollowedException,
                    ProfileNotExistsException,
                    QueryReturnedForbiddenException,
                    QueryReturnedNotFoundException,
                    TooManyRequestsException,
                    TwoFactorAuthRequiredException,
                )

                L = self._init_instaloader(destination, auth)
                target_type = (context and context.get("content_type")) or target.content_type
                username = target.username

                items_downloaded = 0
                items_skipped = 0
                items_discovered = 0

                if target_type in ("profile", "photos", "videos"):
                    if not username:
                        return DownloadResult(
                            status=DownloadResultStatus.FAILED,
                            extractor=self.name,
                            failure_type=FailureType.NOT_FOUND,
                            message="No username provided for Instagram profile",
                        )
                    profile = instaloader.Profile.from_username(L.context, username)
                    posts = profile.get_posts()
                    for post in posts:
                        items_discovered += 1
                        # Filter photo/video if specified
                        if target_type == "photos" and post.is_video:
                            items_skipped += 1
                            continue
                        if target_type == "videos" and not post.is_video:
                            items_skipped += 1
                            continue

                        downloaded = L.download_post(post, target=username)
                        if downloaded:
                            items_downloaded += 1
                        else:
                            items_skipped += 1

                elif target_type == "story":
                    if not username:
                        return DownloadResult(
                            status=DownloadResultStatus.FAILED,
                            extractor=self.name,
                            failure_type=FailureType.NOT_FOUND,
                            message="No username provided for Instagram stories",
                        )
                    profile = instaloader.Profile.from_username(L.context, username)
                    user_id = profile.userid
                    for story in L.get_stories(userids=[user_id]):
                        for item in story.get_items():
                            items_discovered += 1
                            downloaded = L.download_storyitem(item, target=username)
                            if downloaded:
                                items_downloaded += 1
                            else:
                                items_skipped += 1

                elif target_type == "highlight":
                    if not username:
                        return DownloadResult(
                            status=DownloadResultStatus.FAILED,
                            extractor=self.name,
                            failure_type=FailureType.NOT_FOUND,
                            message="No username provided for Instagram highlights",
                        )
                    profile = instaloader.Profile.from_username(L.context, username)
                    for highlight in L.get_highlights(profile):
                        for item in highlight.get_items():
                            items_discovered += 1
                            downloaded = L.download_storyitem(item, target=f"{username}_highlights")
                            if downloaded:
                                items_downloaded += 1
                            else:
                                items_skipped += 1

                elif target_type in ("reel", "reels"):
                    if not username:
                        return DownloadResult(
                            status=DownloadResultStatus.FAILED,
                            extractor=self.name,
                            failure_type=FailureType.NOT_FOUND,
                            message="No username provided for Instagram reels",
                        )
                    profile = instaloader.Profile.from_username(L.context, username)
                    for reel in profile.get_reels():
                        items_discovered += 1
                        downloaded = L.download_post(reel, target=f"{username}_reels")
                        if downloaded:
                            items_downloaded += 1
                        else:
                            items_skipped += 1

                elif target_type == "post" and target.content_id:
                    post = instaloader.Post.from_shortcode(L.context, target.content_id)
                    items_discovered += 1
                    downloaded = L.download_post(post, target="single_post")
                    if downloaded:
                        items_downloaded += 1
                    else:
                        items_skipped += 1

                return DownloadResult(
                    status=DownloadResultStatus.SUCCESS,
                    extractor=self.name,
                    items_discovered=items_discovered,
                    items_downloaded=items_downloaded,
                    items_skipped=items_skipped,
                    message="Completed successfully",
                )

            except (
                BadCredentialsException,
                LoginException,
                LoginRequiredException,
                TwoFactorAuthRequiredException,
                QueryReturnedForbiddenException,
            ) as e:
                return DownloadResult(
                    status=DownloadResultStatus.FAILED,
                    extractor=self.name,
                    failure_type=FailureType.AUTH,
                    message=f"Instaloader Auth Error: {e}",
                )

            except TooManyRequestsException as e:
                return DownloadResult(
                    status=DownloadResultStatus.FAILED,
                    extractor=self.name,
                    failure_type=FailureType.RATE_LIMIT,
                    message=f"Instaloader Rate Limit: {e}",
                )

            except (
                ProfileNotExistsException,
                QueryReturnedNotFoundException,
                PrivateProfileNotFollowedException,
            ) as e:
                return DownloadResult(
                    status=DownloadResultStatus.FAILED,
                    extractor=self.name,
                    failure_type=FailureType.NOT_FOUND,
                    message=f"Instaloader Not Found: {e}",
                )

            except ConnectionException as e:
                return DownloadResult(
                    status=DownloadResultStatus.FAILED,
                    extractor=self.name,
                    failure_type=FailureType.NETWORK,
                    message=f"Instaloader Network Error: {e}",
                )

            except InvalidArgumentException as e:
                return DownloadResult(
                    status=DownloadResultStatus.FAILED,
                    extractor=self.name,
                    failure_type=FailureType.EXTRACTOR,
                    message=f"Instaloader Invalid Argument: {e}",
                )

            except Exception as e:
                return DownloadResult(
                    status=DownloadResultStatus.FAILED,
                    extractor=self.name,
                    failure_type=FailureType.EXTRACTOR,
                    message=f"Instaloader Error: {e}",
                )
