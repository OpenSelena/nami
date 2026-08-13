"""Extractor capability registry and deterministic engine manager for Nami."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nami.auth import AuthConfig
from nami.extractors import EXTRACTORS
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.retry import FailureType

logger = logging.getLogger(__name__)

EXTRACTOR_CAPABILITIES: dict[str, dict[str, set[str]]] = {
    "instaloader": {
        "instagram": {"profile", "post", "reel", "story", "highlight", "photos", "videos"},
    },
    "gallery-dl": {
        "instagram": {"profile", "post", "reel", "story", "highlight", "photos", "videos"},
        "tiktok": {"profile", "post", "video", "photos", "videos"},
        "facebook": {"profile", "post", "video", "photos", "videos"},
        "x": {"profile", "post", "video", "photos", "videos"},
    },
    "yt-dlp": {
        "instagram": {"post", "reel", "video", "videos"},
        "tiktok": {"profile", "video", "videos"},
        "facebook": {"video", "videos"},
        "x": {"video", "videos"},
    },
}

EXTRACTION_PLANS: dict[str, dict[str, list[str]]] = {
    "instagram": {
        "profile": ["gallery-dl", "instaloader"],
        "photos": ["gallery-dl", "instaloader"],
        "post": ["gallery-dl", "instaloader"],
        "videos": ["gallery-dl", "yt-dlp", "instaloader"],
        "video": ["gallery-dl", "yt-dlp", "instaloader"],
        "reel": ["instaloader", "yt-dlp", "gallery-dl"],
        "reels": ["instaloader", "yt-dlp", "gallery-dl"],
        "story": ["instaloader", "gallery-dl"],
        "stories": ["instaloader", "gallery-dl"],
        "highlight": ["instaloader", "gallery-dl"],
        "highlights": ["instaloader", "gallery-dl"],
    },
    "tiktok": {
        "photos": ["gallery-dl"],
        "videos": ["yt-dlp", "gallery-dl"],
        "video": ["yt-dlp", "gallery-dl"],
        "profile": ["yt-dlp", "gallery-dl"],
    },
    "facebook": {
        "photos": ["gallery-dl"],
        "videos": ["yt-dlp", "gallery-dl"],
        "video": ["yt-dlp", "gallery-dl"],
        "profile": ["yt-dlp", "gallery-dl"],
    },
    "x": {
        "photos": ["gallery-dl"],
        "videos": ["yt-dlp", "gallery-dl"],
        "video": ["yt-dlp", "gallery-dl"],
        "profile": ["yt-dlp", "gallery-dl"],
    },
}


class ExtractorManager:
    """Deterministic Extractor Manager that selects and orchestrates engines based on plan and capabilities."""

    def get_plan(self, platform: str, content_type: str) -> list[str]:
        plat = platform.lower()
        content = content_type.lower()
        platform_plan = EXTRACTION_PLANS.get(plat, {})
        plan = platform_plan.get(content)
        if not plan:
            # Fallback to default platform order
            if plat == "instagram":
                plan = ["gallery-dl", "instaloader", "yt-dlp"]
            else:
                plan = ["yt-dlp", "gallery-dl"]
        return plan

    def is_fallback_allowed(self, failure_type: FailureType | None) -> bool:
        """
        Determines whether falling back to another engine is allowed.
        Strictly disallowed for AUTH, RATE_LIMIT, NETWORK, NOT_FOUND, DEPENDENCY, UNKNOWN, TIMEOUT.
        Only EXTRACTOR and UNSUPPORTED allow fallback.
        """
        if failure_type in (
            FailureType.AUTH,
            FailureType.RATE_LIMIT,
            FailureType.NETWORK,
            FailureType.NOT_FOUND,
            FailureType.DEPENDENCY,
            FailureType.UNKNOWN,
            FailureType.TIMEOUT,
        ):
            return False
        return True

    def download(
        self,
        target: ParsedTarget,
        content_type: str,
        destination: Path,
        auth: AuthConfig,
        progress_obj: Any = None,
        active_task_id: Any = None,
        context: dict[str, Any] | None = None,
    ) -> DownloadResult:
        plat = target.platform.lower()
        plan = self.get_plan(plat, content_type)

        primary_extractor_name = plan[0] if plan else None
        last_result: DownloadResult | None = None
        used_fallback = False

        for idx, engine_name in enumerate(plan):
            extractor = EXTRACTORS.get(engine_name)
            if not extractor:
                continue

            # Verify capability registry
            caps = EXTRACTOR_CAPABILITIES.get(engine_name, {}).get(plat, set())
            if content_type.lower() not in caps and not extractor.supports(plat, content_type):
                continue

            if idx > 0:
                used_fallback = True

            exec_context = dict(context) if context else {}
            exec_context["content_type"] = content_type

            result = extractor.download(
                target=target,
                destination=destination,
                auth=auth,
                progress_obj=progress_obj,
                active_task_id=active_task_id,
                context=exec_context,
            )

            last_result = result
            if result.status == DownloadResultStatus.SUCCESS:
                if used_fallback and primary_extractor_name:
                    result.fallback_extractor = f"fallback: {engine_name}"
                return result

            # Check if fallback is permitted for this failure type
            if not self.is_fallback_allowed(result.failure_type):
                return result

        if last_result is not None:
            return last_result

        return DownloadResult(
            status=DownloadResultStatus.UNSUPPORTED,
            failure_type=FailureType.EXTRACTOR,
            message=f"No suitable extractor available for {plat} / {content_type}",
        )
