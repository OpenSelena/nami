"""Deterministic, side-effect-free download planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nami.config import Settings
from nami.models import MediaKind, Platform, Target
from nami.targets import resolve_target_endpoints, safe_target_dir

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
    endpoints = resolve_target_endpoints(target, media)
    steps: list[PlanStep] = []
    for endpoint in endpoints:
        label = f"{base_label}:{endpoint.suffix_label}" if endpoint.suffix_label else base_label
        engines: tuple[str, ...]
        if not endpoint.supported:
            engines = ()
        elif media is MediaKind.VIDEOS:
            engines = ("gallery-dl", "yt-dlp")
        else:
            engines = ("gallery-dl",)
        steps.append(
            PlanStep(
                label=label,
                target=target,
                media=media,
                destination=destination,
                url=endpoint.url,
                engines=engines,
                supported=endpoint.supported,
                reason=endpoint.reason,
            )
        )
    return tuple(steps)


def _coerce_media(value: MediaKind | str) -> MediaKind:
    if isinstance(value, MediaKind):
        return value
    try:
        return MediaKind(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"unsupported media kind: {value}") from exc
