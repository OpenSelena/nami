"""Deterministic, side-effect-free download planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nami.config import Settings
from nami.models import MediaKind, Platform, Target
from nami.targets import safe_target_dir

_MEDIA_ORDER = {
    MediaKind.PHOTOS: 0,
    MediaKind.VIDEOS: 1,
    MediaKind.STORIES: 2,
    MediaKind.HIGHLIGHTS: 3,
}
_DESTINATION_NAMES = {
    MediaKind.PHOTOS: "Photos",
    MediaKind.VIDEOS: "Videos",
    MediaKind.STORIES: "Stories",
    MediaKind.HIGHLIGHTS: "Highlights",
}


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """Immutable inputs for one batch of download operations."""

    targets: tuple[Target, ...]
    media: tuple[MediaKind, ...] | frozenset[MediaKind]
    settings: Settings

    def __post_init__(self) -> None:
        targets = tuple(self.targets)
        requested_media = tuple(_coerce_media(value) for value in self.media)
        ordered_media = tuple(sorted(set(requested_media), key=_MEDIA_ORDER.__getitem__))
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "media", ordered_media)


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One independently executable operation in a download plan."""

    label: str
    target: Target
    media: MediaKind
    destination: Path
    url: str
    engines: tuple[str, ...]
    supported: bool = True
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "destination", Path(self.destination))
        object.__setattr__(self, "engines", tuple(self.engines))
        if not self.label:
            raise ValueError("plan step label must not be empty")
        if not self.url:
            raise ValueError("plan step URL must not be empty")
        if self.supported and not self.engines:
            raise ValueError("supported plan steps require at least one engine")
        if not self.supported and self.engines:
            raise ValueError("unsupported plan steps must not name engines")

    @property
    def media_kind(self) -> MediaKind:
        """Compatibility alias matching the result model's terminology."""

        return self.media

    @property
    def engine_names(self) -> tuple[str, ...]:
        """Return downloader engines in fallback order."""

        return self.engines


def build_plan(request: DownloadRequest) -> tuple[PlanStep, ...]:
    """Build a deterministic plan without creating any directories."""

    steps: list[PlanStep] = []
    seen: set[tuple[Platform, str, Path]] = set()

    for target in request.targets:
        target_root = safe_target_dir(request.settings.base_dir, target)
        for media in request.media:
            destination = target_root / _DESTINATION_NAMES[media]
            for step in _steps_for_target(target, media, destination):
                identity = (target.platform, step.label, destination)
                if identity in seen:
                    continue
                seen.add(identity)
                steps.append(step)
    return tuple(steps)


def _steps_for_target(target: Target, media: MediaKind, destination: Path) -> tuple[PlanStep, ...]:
    base_label = f"{target.platform.value}:{target.target_key}:{media.value}"

    if target.content_type != "profile":
        supported, reason = _direct_support(target, media)
        return (
            _step(
                base_label,
                target,
                media,
                destination,
                target.canonical_url,
                supported=supported,
                reason=reason,
            ),
        )

    if media is MediaKind.VIDEOS and target.platform is Platform.INSTAGRAM:
        username = _require_username(target)
        return (
            _step(
                f"{base_label}:feed",
                target,
                media,
                destination,
                target.canonical_url,
            ),
            _step(
                f"{base_label}:reels",
                target,
                media,
                destination,
                f"https://www.instagram.com/{username}/reels/",
            ),
        )

    if media is MediaKind.STORIES:
        if target.platform is not Platform.INSTAGRAM:
            return (_unsupported(base_label, target, media, destination),)
        username = _require_username(target)
        return (
            _step(
                base_label,
                target,
                media,
                destination,
                f"https://www.instagram.com/stories/{username}/",
            ),
        )

    if media is MediaKind.HIGHLIGHTS:
        if target.platform is not Platform.INSTAGRAM:
            return (_unsupported(base_label, target, media, destination),)
        username = _require_username(target)
        return (
            _step(
                base_label,
                target,
                media,
                destination,
                f"https://www.instagram.com/{username}/highlights/",
            ),
        )

    return (
        _step(
            base_label,
            target,
            media,
            destination,
            target.canonical_url,
        ),
    )


def _direct_support(target: Target, media: MediaKind) -> tuple[bool, str | None]:
    if media in {MediaKind.PHOTOS, MediaKind.VIDEOS}:
        return True, None
    if target.platform is Platform.INSTAGRAM:
        if media is MediaKind.STORIES and target.content_type == "story":
            return True, None
        if media is MediaKind.HIGHLIGHTS and target.content_type == "highlight":
            return True, None
    return False, _unsupported_reason(target, media)


def _step(
    label: str,
    target: Target,
    media: MediaKind,
    destination: Path,
    url: str,
    *,
    supported: bool = True,
    reason: str | None = None,
) -> PlanStep:
    engines: tuple[str, ...]
    if not supported:
        engines = ()
    elif media is MediaKind.PHOTOS:
        engines = ("gallery-dl",)
    elif media is MediaKind.VIDEOS:
        engines = ("gallery-dl", "yt-dlp")
    else:
        engines = ("gallery-dl",)
    return PlanStep(
        label=label,
        target=target,
        media=media,
        destination=destination,
        url=url,
        engines=engines,
        supported=supported,
        reason=reason,
    )


def _unsupported(label: str, target: Target, media: MediaKind, destination: Path) -> PlanStep:
    return _step(
        label,
        target,
        media,
        destination,
        target.canonical_url,
        supported=False,
        reason=_unsupported_reason(target, media),
    )


def _unsupported_reason(target: Target, media: MediaKind) -> str:
    return f"{media.value} are not supported for {target.platform.value} {target.content_type} targets"


def _require_username(target: Target) -> str:
    if target.username is None:
        raise ValueError("profile target is missing a username")
    return target.username


def _coerce_media(value: MediaKind | str) -> MediaKind:
    if isinstance(value, MediaKind):
        return value
    try:
        return MediaKind(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"unsupported media kind: {value}") from exc
