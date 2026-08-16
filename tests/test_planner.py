from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nami.config import settings_for_root
from nami.models import MediaKind
from nami.planner import DownloadRequest, build_plan
from nami.targets import parse_target


def test_instagram_profile_plan_has_exact_urls_layout_and_engines(tmp_path: Path) -> None:
    settings = settings_for_root(tmp_path)
    target = parse_target("https://instagram.com/NASA")
    request = DownloadRequest(
        targets=(target,),
        media=frozenset(MediaKind),
        settings=settings,
    )

    steps = build_plan(request)

    assert [step.label for step in steps] == [
        "instagram:nasa:photos",
        "instagram:nasa:videos:feed",
        "instagram:nasa:videos:reels",
        "instagram:nasa:stories",
        "instagram:nasa:highlights",
    ]
    assert [step.url for step in steps] == [
        "https://www.instagram.com/NASA/",
        "https://www.instagram.com/NASA/",
        "https://www.instagram.com/NASA/reels/",
        "https://www.instagram.com/stories/NASA/",
        "https://www.instagram.com/NASA/highlights/",
    ]
    root = settings.base_dir.resolve() / "instagram" / "nasa"
    assert [step.destination for step in steps] == [
        root / "Photos",
        root / "Videos",
        root / "Videos",
        root / "Stories",
        root / "Highlights",
    ]
    assert [step.engines for step in steps] == [
        ("gallery-dl",),
        ("gallery-dl", "yt-dlp"),
        ("gallery-dl", "yt-dlp"),
        ("gallery-dl",),
        ("gallery-dl",),
    ]
    assert all(step.supported for step in steps)
    assert not settings.base_dir.exists()


def test_request_is_immutable_deduplicated_and_deterministic(tmp_path: Path) -> None:
    target = parse_target("https://www.instagram.com/example/")
    request = DownloadRequest(
        targets=(target, target),
        media=(MediaKind.HIGHLIGHTS, MediaKind.PHOTOS, MediaKind.PHOTOS),
        settings=settings_for_root(tmp_path),
    )

    assert request.media == (MediaKind.PHOTOS, MediaKind.HIGHLIGHTS)
    assert len(build_plan(request)) == 2
    with pytest.raises(FrozenInstanceError):
        request.targets = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@creator",
        "https://www.facebook.com/creator/",
        "https://x.com/creator",
    ],
)
def test_non_instagram_stories_and_highlights_are_structured_unsupported(tmp_path: Path, url: str) -> None:
    target = parse_target(url)
    steps = build_plan(
        DownloadRequest(
            (target,),
            (MediaKind.STORIES, MediaKind.HIGHLIGHTS),
            settings_for_root(tmp_path),
        )
    )

    assert len(steps) == 2
    assert all(not step.supported for step in steps)
    assert all(step.engines == () for step in steps)
    assert all(step.reason and "not supported" in step.reason for step in steps)


def test_direct_targets_use_canonical_urls_and_unique_target_directories(
    tmp_path: Path,
) -> None:
    settings = settings_for_root(tmp_path)
    first = parse_target("https://instagram.com/p/AAA?ignored=yes")
    second = parse_target("https://instagram.com/p/BBB")

    steps = build_plan(DownloadRequest((first, second), (MediaKind.PHOTOS, MediaKind.VIDEOS), settings))

    assert [step.url for step in steps] == [
        first.canonical_url,
        first.canonical_url,
        second.canonical_url,
        second.canonical_url,
    ]
    assert {step.destination.parent for step in steps} == {
        settings.base_dir.resolve() / "instagram" / "post_AAA",
        settings.base_dir.resolve() / "instagram" / "post_BBB",
    }
    assert len({step.label for step in steps}) == 4
