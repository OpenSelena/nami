"""URL and profile target parsing for Nami."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

VALID_DOMAINS = {
    "instagram": ["instagram.com"],
    "tiktok": ["tiktok.com"],
    "facebook": ["facebook.com"],
    "x": ["x.com", "twitter.com"],
}

NON_PROFILE_SEGMENTS = {
    "p", "reel", "tv", "highlights", "stories",
    "groups", "events", "hashtag", "i", "explore", "reels"
}


@dataclass
class ParsedTarget:
    platform: str
    username: str | None
    content_type: str  # "profile", "reel", "story", "highlight", etc.
    original_url: str


def parse_url(url: str, platform: str) -> ParsedTarget | None | str:
    """
    Parse a URL or username string for a given platform.
    Returns:
    - ParsedTarget if valid profile/content target detected
    - None if valid domain/format but no username could be resolved
    - "INVALID_URL" if domain or format is invalid/mismatched
    """
    original_url = url
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()

        for prefix in ("www.", "m.", "mobile.", "vm.", "business."):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
                break

        allowed = VALID_DOMAINS.get(platform.lower(), [])
        if domain not in allowed:
            return "INVALID_URL"

        path = parsed.path.strip("/")
        path_parts = [p for p in path.split("/") if p]
        if not path_parts:
            return None

        # Facebook numeric ID format: /profile.php?id=123456789
        if platform == "facebook" and path_parts[0].lower() == "profile.php":
            query = urllib.parse.parse_qs(parsed.query)
            ids = query.get("id")
            if ids and ids[0].isdigit():
                return ParsedTarget(
                    platform=platform,
                    username=ids[0],
                    content_type="profile",
                    original_url=original_url,
                )
            return None

        first_part = path_parts[0].replace("@", "").split("?")[0].split("#")[0]

        # Check specific routes
        if first_part.lower() == "stories" and len(path_parts) > 1:
            username = path_parts[1].replace("@", "").split("?")[0].split("#")[0]
            return ParsedTarget(
                platform=platform,
                username=username if username else None,
                content_type="story",
                original_url=original_url,
            )

        if len(path_parts) > 1 and path_parts[1].lower() == "highlights":
            return ParsedTarget(
                platform=platform,
                username=first_part,
                content_type="highlight",
                original_url=original_url,
            )

        if len(path_parts) > 1 and path_parts[1].lower() == "reels":
            return ParsedTarget(
                platform=platform,
                username=first_part,
                content_type="reel",
                original_url=original_url,
            )

        if first_part.lower() in NON_PROFILE_SEGMENTS:
            return None

        return ParsedTarget(
            platform=platform,
            username=first_part if first_part else None,
            content_type="profile",
            original_url=original_url,
        )
    except Exception:
        return "INVALID_URL"
