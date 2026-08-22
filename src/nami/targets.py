"""Strict target parsing and filesystem-safe target discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .config import Settings
from .models import MediaKind, Platform, Target

_HOSTS = {
    Platform.INSTAGRAM: frozenset(
        {
            "instagram.com",
            "www.instagram.com",
            "m.instagram.com",
            "mobile.instagram.com",
        }
    ),
    Platform.TIKTOK: frozenset({"tiktok.com", "www.tiktok.com", "m.tiktok.com", "mobile.tiktok.com"}),
    Platform.FACEBOOK: frozenset(
        {
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
            "mobile.facebook.com",
            "mbasic.facebook.com",
            "web.facebook.com",
            "business.facebook.com",
            "fb.com",
            "www.fb.com",
        }
    ),
    Platform.X: frozenset(
        {
            "x.com",
            "www.x.com",
            "mobile.x.com",
            "twitter.com",
            "www.twitter.com",
            "mobile.twitter.com",
        }
    ),
}
_SHORT_TIKTOK_HOSTS = frozenset({"vm.tiktok.com", "vt.tiktok.com"})
_CANONICAL_HOST = {
    Platform.INSTAGRAM: "www.instagram.com",
    Platform.TIKTOK: "www.tiktok.com",
    Platform.FACEBOOK: "www.facebook.com",
    Platform.X: "x.com",
}
_RESERVED = {
    Platform.INSTAGRAM: frozenset(
        {
            "accounts",
            "about",
            "api",
            "developer",
            "direct",
            "directory",
            "emails",
            "explore",
            "legal",
            "p",
            "privacy",
            "reel",
            "reels",
            "stories",
            "terms",
            "tv",
        }
    ),
    Platform.TIKTOK: frozenset(
        {
            "about",
            "business-suite",
            "discover",
            "explore",
            "foryou",
            "legal",
            "login",
            "music",
            "search",
            "tag",
        }
    ),
    Platform.FACEBOOK: frozenset(
        {
            "about",
            "business",
            "events",
            "gaming",
            "groups",
            "help",
            "login",
            "marketplace",
            "pages",
            "photo.php",
            "privacy",
            "reel",
            "share",
            "stories",
            "watch",
        }
    ),
    Platform.X: frozenset(
        {
            "compose",
            "explore",
            "hashtag",
            "home",
            "i",
            "intent",
            "login",
            "messages",
            "notifications",
            "search",
            "settings",
            "share",
        }
    ),
}
_USERNAME_PATTERNS = {
    Platform.INSTAGRAM: re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9._]{0,28}[A-Za-z0-9_])?\Z"),
    Platform.TIKTOK: re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9._]{0,22}[A-Za-z0-9_])?\Z"),
    Platform.FACEBOOK: re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,78}[A-Za-z0-9])?\Z"),
    Platform.X: re.compile(r"[A-Za-z0-9_]{1,15}\Z"),
}
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")
_SAFE_TARGET_KEY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,239}\Z")
_WINDOWS_DRIVE = re.compile(r"(?:^|[\\/])[A-Za-z]:[\\/]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class TargetParseError(ValueError):
    """A safe, contextual error raised for an invalid target."""

    def __init__(
        self,
        message: str,
        *,
        raw: str | None = None,
        source: Path | None = None,
        line_number: int | None = None,
    ) -> None:
        super().__init__(message)
        self.raw = raw
        self.source = source
        self.line_number = line_number


def parse_target(raw: str, platform_hint: Platform | str | None = None) -> Target:
    """Parse a supported HTTP(S) URL into a canonical immutable target."""
    if not isinstance(raw, str):
        raise TargetParseError("target must be a URL string")
    original = raw.strip()
    if not original:
        raise TargetParseError("target URL is empty", raw=raw)
    if _CONTROL.search(original):
        raise TargetParseError("target URL contains control characters", raw=raw)
    if "\\" in original or _WINDOWS_DRIVE.search(original):
        raise TargetParseError("target URL contains an unsafe Windows path", raw=raw)

    try:
        parsed = urlsplit(original)
        port = parsed.port
    except ValueError as exc:
        raise TargetParseError(f"malformed target URL: {exc}", raw=raw) from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise TargetParseError("target URL must use http or https", raw=raw)
    if not parsed.netloc or parsed.hostname is None:
        raise TargetParseError("target URL is missing a supported host", raw=raw)
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise TargetParseError("target URL must not contain credentials or a port", raw=raw)

    host = parsed.hostname.lower().rstrip(".")
    if host in _SHORT_TIKTOK_HOSTS:
        raise TargetParseError(
            "TikTok short links are not accepted; use the resolved tiktok.com URL",
            raw=raw,
        )
    inferred = _platform_for_host(host)
    if inferred is None:
        raise TargetParseError(f"unsupported target host: {host}", raw=raw)

    hinted = _coerce_platform(platform_hint) if platform_hint is not None else None
    if hinted is not None and hinted is not inferred:
        raise TargetParseError(f"target host belongs to {inferred.value}, not {hinted.value}", raw=raw)
    platform = inferred

    segments = _path_segments(parsed.path, raw)
    if platform is Platform.INSTAGRAM:
        username, content_type, content_id, canonical_path = _parse_instagram(segments)
    elif platform is Platform.TIKTOK:
        username, content_type, content_id, canonical_path = _parse_tiktok(segments)
    elif platform is Platform.FACEBOOK:
        username, content_type, content_id, canonical_path = _parse_facebook(segments, parsed.query)
    else:
        username, content_type, content_id, canonical_path = _parse_x(segments)

    canonical_url = f"https://{_CANONICAL_HOST[platform]}{canonical_path}"
    target_key = _target_key(username, content_type, content_id)
    return Target(
        original_url=original,
        canonical_url=canonical_url,
        target_key=target_key,
        platform=platform,
        username=username,
        content_type=content_type,
        content_id=content_id,
    )


@dataclass(frozen=True, slots=True)
class TargetEndpoint:
    """One resolved download endpoint for a target and media kind."""

    url: str
    suffix_label: str = ""
    supported: bool = True
    reason: str | None = None


def resolve_target_endpoints(target: Target, media: MediaKind) -> tuple[TargetEndpoint, ...]:
    """Resolve endpoint URLs and support status for a target and media kind."""
    if target.content_type != "profile":
        if media in {MediaKind.PHOTOS, MediaKind.VIDEOS}:
            return (TargetEndpoint(target.canonical_url),)
        if target.platform is Platform.INSTAGRAM:
            if media is MediaKind.STORIES and target.content_type == "story":
                return (TargetEndpoint(target.canonical_url),)
            if media is MediaKind.HIGHLIGHTS and target.content_type == "highlight":
                return (TargetEndpoint(target.canonical_url),)
        return (
            TargetEndpoint(
                target.canonical_url,
                supported=False,
                reason=f"{media.value} are not supported for {target.platform.value} {target.content_type} targets",
            ),
        )

    if media is MediaKind.VIDEOS and target.platform is Platform.INSTAGRAM:
        username = target.username
        if username is None:
            raise ValueError("profile target is missing a username")
        return (
            TargetEndpoint(target.canonical_url, suffix_label="feed"),
            TargetEndpoint(f"https://www.instagram.com/{username}/reels/", suffix_label="reels"),
        )

    if media is MediaKind.STORIES:
        if target.platform is not Platform.INSTAGRAM:
            return (
                TargetEndpoint(
                    target.canonical_url,
                    supported=False,
                    reason=f"{media.value} are not supported for {target.platform.value} {target.content_type} targets",
                ),
            )
        username = target.username
        if username is None:
            raise ValueError("profile target is missing a username")
        return (TargetEndpoint(f"https://www.instagram.com/stories/{username}/"),)

    if media is MediaKind.HIGHLIGHTS:
        if target.platform is not Platform.INSTAGRAM:
            return (
                TargetEndpoint(
                    target.canonical_url,
                    supported=False,
                    reason=f"{media.value} are not supported for {target.platform.value} {target.content_type} targets",
                ),
            )
        username = target.username
        if username is None:
            raise ValueError("profile target is missing a username")
        return (TargetEndpoint(f"https://www.instagram.com/{username}/highlights/"),)

    return (TargetEndpoint(target.canonical_url),)



def safe_target_dir(base_dir: Path | str, target: Target) -> Path:
    """Resolve a target directory and prove it remains below base/platform."""
    if not isinstance(target.platform, Platform):
        raise TypeError("target has an unsupported platform")
    key = target.target_key
    if (
        not _SAFE_TARGET_KEY.fullmatch(key)
        or key in {".", ".."}
        or ".." in key.split("/")
        or "\\" in key
        or "/" in key
        or ":" in key
        or _CONTROL.search(key)
    ):
        raise ValueError("target_key is not filesystem-safe")

    base_root = Path(base_dir).expanduser().resolve()
    platform_root = (base_root / target.platform.value).resolve()
    candidate = (platform_root / key).resolve()
    try:
        platform_root.relative_to(base_root)
        candidate.relative_to(platform_root)
    except ValueError as exc:
        raise ValueError("target directory escapes the platform directory") from exc
    return candidate


def load_profile_targets(
    settings: Settings,
    platforms: list[Platform | str] | tuple[Platform | str, ...] | None = None,
) -> tuple[list[Target], list[TargetParseError]]:
    """Load target files in deterministic order without changing the process cwd."""
    selected = list(Platform) if platforms is None else [_coerce_platform(platform) for platform in platforms]
    targets: list[Target] = []
    errors: list[TargetParseError] = []
    seen: set[tuple[Platform, str]] = set()

    for platform in selected:
        source = settings.profiles_dir / f"{platform.value}_profiles.txt"
        if not source.exists():
            continue
        try:
            lines = source.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            errors.append(TargetParseError(f"could not read {source.name}: {exc}", source=source))
            continue
        for line_number, line in enumerate(lines, start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            try:
                target = parse_target(raw, platform)
            except TargetParseError as exc:
                errors.append(TargetParseError(str(exc), raw=raw, source=source, line_number=line_number))
                continue
            identity = (target.platform, target.canonical_url)
            if identity not in seen:
                seen.add(identity)
                targets.append(target)
    return targets, errors


def _coerce_platform(value: Platform | str) -> Platform:
    if isinstance(value, Platform):
        return value
    normalized = str(value).strip().lower()
    if normalized == "twitter":
        normalized = "x"
    try:
        return Platform(normalized)
    except ValueError as exc:
        raise TargetParseError(f"unsupported platform: {value}") from exc


def _platform_for_host(host: str) -> Platform | None:
    for platform, hosts in _HOSTS.items():
        if host in hosts:
            return platform
    return None


def _path_segments(path: str, raw: str) -> list[str]:
    segments: list[str] = []
    for encoded in path.split("/"):
        if not encoded:
            continue
        segment = unquote(encoded)
        if (
            not segment
            or segment in {".", ".."}
            or "/" in segment
            or "\\" in segment
            or ":" in segment
            or _CONTROL.search(segment)
        ):
            raise TargetParseError("target URL contains an unsafe path segment", raw=raw)
        segments.append(segment)
    if not segments:
        raise TargetParseError("target URL does not identify a profile or content item", raw=raw)
    return segments


def _validate_username(platform: Platform, raw: str) -> str:
    username = raw[1:] if platform is Platform.TIKTOK and raw.startswith("@") else raw
    if not _USERNAME_PATTERNS[platform].fullmatch(username):
        raise TargetParseError(f"invalid {platform.value} username")
    if ".." in username or username.casefold() in _RESERVED[platform]:
        raise TargetParseError(f"URL route is not a {platform.value} profile")
    return username


def _validate_id(value: str, *, numeric: bool = False) -> str:
    if (numeric and not value.isdigit()) or not _SAFE_ID.fullmatch(value):
        raise TargetParseError("invalid content identifier")
    return value


def _require_length(segments: list[str], expected: int, route: str) -> None:
    if len(segments) != expected:
        raise TargetParseError(f"invalid {route} URL route")


def _parse_instagram(
    segments: list[str],
) -> tuple[str | None, str, str | None, str]:
    route = segments[0].casefold()
    if route in {"p", "reel", "tv"}:
        _require_length(segments, 2, f"Instagram {route}")
        content_id = _validate_id(segments[1])
        content_type = "post" if route == "p" else "reel"
        canonical_route = "p" if route == "p" else "reel"
        return None, content_type, content_id, f"/{canonical_route}/{content_id}/"
    if route == "stories":
        if len(segments) == 3 and segments[1].casefold() == "highlights":
            content_id = _validate_id(segments[2])
            return None, "highlight", content_id, f"/stories/highlights/{content_id}/"
        if len(segments) not in {2, 3}:
            raise TargetParseError("invalid Instagram story URL route")
        username = _validate_username(Platform.INSTAGRAM, segments[1])
        content_id = _validate_id(segments[2]) if len(segments) == 3 else None
        suffix = f"/{content_id}" if content_id is not None else ""
        return username, "story", content_id, f"/stories/{username}{suffix}/"
    _require_length(segments, 1, "Instagram profile")
    username = _validate_username(Platform.INSTAGRAM, segments[0])
    return username, "profile", None, f"/{username}/"


def _parse_tiktok(
    segments: list[str],
) -> tuple[str | None, str, str | None, str]:
    if not segments[0].startswith("@"):
        raise TargetParseError("TikTok profile URLs must use /@username")
    username = _validate_username(Platform.TIKTOK, segments[0])
    if len(segments) == 1:
        return username, "profile", None, f"/@{username}"
    if len(segments) == 3 and segments[1].casefold() == "video":
        content_id = _validate_id(segments[2], numeric=True)
        return username, "video", content_id, f"/@{username}/video/{content_id}"
    raise TargetParseError("invalid TikTok URL route")


def _parse_facebook(segments: list[str], query: str) -> tuple[str | None, str, str | None, str]:
    route = segments[0].casefold()
    query_values = parse_qs(query, keep_blank_values=True)
    if route == "profile.php":
        _require_length(segments, 1, "Facebook profile.php")
        ids = query_values.get("id", [])
        if len(ids) != 1 or not ids[0].isdigit():
            raise TargetParseError("Facebook profile.php requires one numeric id")
        username = ids[0]
        return username, "profile", None, f"/profile.php?id={username}"
    if route == "watch":
        _require_length(segments, 1, "Facebook watch")
        ids = query_values.get("v", [])
        if len(ids) != 1:
            raise TargetParseError("Facebook watch URL requires one video id")
        content_id = _validate_id(ids[0])
        return None, "video", content_id, f"/watch/?v={content_id}"
    if route == "reel":
        _require_length(segments, 2, "Facebook reel")
        content_id = _validate_id(segments[1])
        return None, "video", content_id, f"/reel/{content_id}/"
    username = _validate_username(Platform.FACEBOOK, segments[0])
    if len(segments) == 1:
        return username, "profile", None, f"/{username}/"
    if len(segments) == 3 and segments[1].casefold() in {"posts", "videos"}:
        content_id = _validate_id(segments[2])
        content_type = "post" if segments[1].casefold() == "posts" else "video"
        return username, content_type, content_id, f"/{username}/{segments[1].casefold()}/{content_id}/"
    raise TargetParseError("invalid Facebook URL route")


def _parse_x(segments: list[str]) -> tuple[str | None, str, str | None, str]:
    username = _validate_username(Platform.X, segments[0])
    if len(segments) == 1:
        return username, "profile", None, f"/{username}"
    if len(segments) == 3 and segments[1].casefold() == "status":
        content_id = _validate_id(segments[2], numeric=True)
        return username, "post", content_id, f"/{username}/status/{content_id}"
    raise TargetParseError("invalid X URL route")


def _target_key(username: str | None, content_type: str, content_id: str | None) -> str:
    if content_type == "profile" and username is not None:
        return username.casefold()
    parts = [username.casefold() if username else None, content_type, content_id]
    key = "_".join(part for part in parts if part)
    if not _SAFE_TARGET_KEY.fullmatch(key):
        raise TargetParseError("target cannot be represented safely on disk")
    return key
