"""gallery-dl engine adapter."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable

from nami.auth import auth_cli_args
from nami.engines.base import (
    EngineAnalysis,
    EngineRequest,
    model_token,
    target_platform_token,
)
from nami.models import MediaKind, Target
from nami.process import CommandSpec

_PHOTO_FILTER = "extension in ('jpg','jpeg','png','gif','webp','bmp','jfif','heic','avif','tiff','svg')"
_VIDEO_FILTER = (
    "extension in ('mp4','webm','mkv','mov','avi','m4v','flv','wmv','3gp','mpeg','mpg','ts','f4v','mts','m2ts')"
)
_MEDIA_PATH_RE = re.compile(
    r"^(?!https?://)(?=.*[\\/]).+\."
    r"(?:jpe?g|png|gif|webp|bmp|jfif|heic|avif|tiff|svg|"
    r"mp4|webm|mkv|mov|avi|m4v|flv|wmv|3gp|mpe?g|mpg|ts|f4v|mts|m2ts)$",
    re.IGNORECASE,
)


class GalleryDlEngine:
    """Construct deterministic gallery-dl commands."""

    name: str = "gallery-dl"

    def __init__(self, *, request_sleep_seconds: float = 5.0) -> None:
        if request_sleep_seconds < 0:
            raise ValueError("request_sleep_seconds must not be negative")
        self._request_sleep_seconds: float = request_sleep_seconds

    def supports(self, target: Target, media: MediaKind) -> bool:
        platform = target_platform_token(target)
        media_name = model_token(media)
        platform_supported = not platform or platform in {
            "facebook",
            "instagram",
            "tiktok",
            "twitter",
            "x",
        }
        media_supported = media_name in {
            "all",
            "highlight",
            "highlights",
            "image",
            "images",
            "mixed",
            "photo",
            "photos",
            "reel",
            "reels",
            "story",
            "stories",
            "video",
            "videos",
        }
        return platform_supported and media_supported

    def build_command(self, request: EngineRequest) -> CommandSpec:
        sleep = f"{self._request_sleep_seconds:g}"
        argv: list[str] = [
            sys.executable,
            "-m",
            "gallery_dl",
            "-D",
            str(request.destination),
            "-o",
            f"user-agent={request.user_agent}",
            "--download-archive",
            str(request.archive),
            "--sleep-request",
            sleep,
        ]

        media = model_token(request.media)
        if media in {"photo", "photos", "image", "images"}:
            argv.extend(("--filter", _PHOTO_FILTER))
        elif media in {"video", "videos", "reel", "reels"}:
            argv.extend(("--filter", _VIDEO_FILTER))

        argv.extend(str(argument) for argument in auth_cli_args(request.auth))
        # The caller owns URL construction. In particular, stories, highlights,
        # and reels URLs must not be rewritten into profile URLs here.
        argv.append(request.url)
        return CommandSpec(tuple(argv), request.timeout_seconds)

    def analyze_output(self, lines: Iterable[str]) -> EngineAnalysis:
        downloaded: set[str] = set()
        archived: set[str] = set()

        for raw_line in lines:
            line = raw_line.strip()
            is_archived = line.startswith("#")
            candidate = line[1:].strip() if is_archived else line
            if not _MEDIA_PATH_RE.fullmatch(candidate):
                continue
            normalized = candidate.casefold()
            if is_archived:
                archived.add(normalized)
            else:
                downloaded.add(normalized)

        return EngineAnalysis(len(downloaded), len(archived))
