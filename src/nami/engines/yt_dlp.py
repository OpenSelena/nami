"""yt-dlp engine adapter."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from urllib.parse import urlsplit

from nami.auth import auth_cli_args
from nami.engines.base import EngineAnalysis, EngineRequest
from nami.models import MediaKind, Platform, Target
from nami.process import CommandSpec

_MEDIA_PATH_RE = re.compile(
    r"^(?!https?://)(?=.*[\\/]).+\."
    r"(?:jpe?g|png|gif|webp|mp4|webm|mkv|mov|avi|m4a|mp3|aac|opus|flac|wav)$",
    re.IGNORECASE,
)
_ARCHIVE_MARKERS = (
    "has already been downloaded",
    "has already been recorded in the archive",
    "has already been recorded in archive",
)
_DIRECT_TARGETS = frozenset(
    {
        "clip",
        "content",
        "direct",
        "highlight",
        "photo",
        "post",
        "reel",
        "short",
        "status",
        "story",
        "tweet",
        "video",
    }
)


class YtDlpEngine:
    """Construct deterministic yt-dlp commands."""

    name: str = "yt-dlp"

    def supports(self, target: Target, media: MediaKind) -> bool:
        platform = target.platform.value if isinstance(target.platform, Platform) else str(target.platform)
        media_name = media.value if isinstance(media, MediaKind) else str(media)
        platform_supported = not platform or platform in {
            "facebook",
            "instagram",
            "tiktok",
            "twitter",
            "x",
            "youtube",
        }
        return platform_supported and media_name in {
            "all",
            "audio",
            "mixed",
            "reel",
            "reels",
            "video",
            "videos",
        }

    def build_command(self, request: EngineRequest) -> CommandSpec:
        output_template = request.destination / "%(extractor)s" / "%(id)s.%(ext)s"
        argv: list[str] = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--output",
            str(output_template),
            "--user-agent",
            request.user_agent,
            "--download-archive",
            str(request.archive),
            "--print",
            "after_move:filepath",
        ]
        if self._is_direct_content(request):
            argv.append("--no-playlist")
        argv.extend(str(argument) for argument in auth_cli_args(request.auth))
        argv.append(request.url)
        return CommandSpec(tuple(argv), request.timeout_seconds)

    def analyze_output(self, lines: Iterable[str]) -> EngineAnalysis:
        downloaded: set[str] = set()
        archived: set[str] = set()

        for raw_line in lines:
            line = raw_line.strip()
            folded = line.casefold()
            if any(marker in folded for marker in _ARCHIVE_MARKERS):
                archived.add(folded)
                continue

            # --print after_move:filepath emits an unprefixed final path. Ignore
            # Destination, merger, and progress lines so one item is not counted
            # at both destination discovery and 100% completion.
            if line.startswith("[") or not _MEDIA_PATH_RE.fullmatch(line):
                continue
            downloaded.add(line.casefold())

        return EngineAnalysis(len(downloaded), len(archived))

    @staticmethod
    def _is_direct_content(request: EngineRequest) -> bool:
        kind = request.target.content_type if hasattr(request.target, "content_type") else str(request.target)
        if kind in _DIRECT_TARGETS:
            return True
        if kind in {"account", "batch", "channel", "playlist", "profile", "user"}:
            return False

        parsed = urlsplit(request.url)
        host = parsed.hostname.casefold() if parsed.hostname else ""
        path_parts = [part.casefold() for part in parsed.path.split("/") if part]
        if host == "youtu.be" and path_parts:
            return True
        if host.endswith("youtube.com") and parsed.path.casefold() == "/watch":
            return True
        return any(
            marker in path_parts for marker in ("p", "post", "reel", "shorts", "status", "story", "video", "watch")
        )
