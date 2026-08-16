from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nami.auth import AuthMode, AuthSpec
from nami.engines.base import EngineRequest
from nami.engines.gallery_dl import GalleryDlEngine
from nami.models import MediaKind, Platform, Target


def request(
    tmp_path: Path,
    *,
    media: MediaKind,
    url: str,
    content_type: str = "profile",
    auth_spec: AuthSpec | None = None,
) -> EngineRequest:
    return EngineRequest(
        target=Target(
            original_url=url,
            canonical_url=url,
            target_key="instagram:example",
            platform=Platform.INSTAGRAM,
            username="example",
            content_type=content_type,
        ),
        media=media,
        destination=tmp_path / "downloads",
        url=url,
        auth=auth_spec or AuthSpec(AuthMode.NONE),
        archive=tmp_path / "archive.txt",
        user_agent="Nami Test Agent",
        timeout_seconds=45,
    )


@pytest.mark.parametrize(
    ("media", "content_type", "url"),
    [
        (MediaKind.STORIES, "story", "https://www.instagram.com/stories/example/123/"),
        (
            MediaKind.HIGHLIGHTS,
            "highlight",
            "https://www.instagram.com/stories/highlights/456/",
        ),
        (MediaKind.VIDEOS, "reel", "https://www.instagram.com/example/reels/"),
    ],
)
def test_build_command_preserves_specialized_instagram_url(
    tmp_path: Path, media: MediaKind, content_type: str, url: str
) -> None:
    spec = GalleryDlEngine().build_command(request(tmp_path, media=media, content_type=content_type, url=url))

    expected_prefix = (
        sys.executable,
        "-m",
        "gallery_dl",
        "-D",
        str(tmp_path / "downloads"),
        "-o",
        "user-agent=Nami Test Agent",
        "--download-archive",
        str(tmp_path / "archive.txt"),
        "--sleep-request",
        "5",
    )
    assert spec.argv[: len(expected_prefix)] == expected_prefix
    assert spec.argv[-1] == url
    assert spec.timeout_seconds == 45


def test_build_command_has_exact_filter_and_cookie_arguments(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies file.txt"
    auth_spec = AuthSpec(AuthMode.COOKIE_FILE, cookie_file=cookie_file)
    url = "https://example.test/profile;touch should-not-run"

    spec = GalleryDlEngine(request_sleep_seconds=2.5).build_command(
        request(tmp_path, media=MediaKind.PHOTOS, url=url, auth_spec=auth_spec)
    )

    assert spec.argv == (
        sys.executable,
        "-m",
        "gallery_dl",
        "-D",
        str(tmp_path / "downloads"),
        "-o",
        "user-agent=Nami Test Agent",
        "--download-archive",
        str(tmp_path / "archive.txt"),
        "--sleep-request",
        "2.5",
        "--filter",
        "extension in ('jpg','jpeg','png','gif','webp','bmp','jfif','heic','avif','tiff','svg')",
        "--cookies",
        str(cookie_file),
        url,
    )
    assert spec.argv.count(url) == 1


def test_analyze_output_only_counts_media_paths() -> None:
    analysis = GalleryDlEngine().analyze_output(
        [
            "/downloads/one.jpg",
            "/downloads/one.jpg",
            "# /downloads/two.mp4",
            "# arbitrary status output",
            "# image.jpg",
            "https://example.test/path/not-a-download.jpg",
            "[gallery-dl] finished",
        ]
    )

    assert analysis.downloaded == 1
    assert analysis.archived == 1
    assert analysis == (1, 1)
