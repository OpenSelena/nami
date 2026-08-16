from __future__ import annotations

import sys
from pathlib import Path

from nami.auth import AuthMode, AuthSpec
from nami.engines.base import EngineRequest
from nami.engines.yt_dlp import YtDlpEngine
from nami.models import MediaKind, Platform, Target


def request(
    tmp_path: Path,
    *,
    content_type: str,
    url: str,
    auth_spec: AuthSpec | None = None,
) -> EngineRequest:
    return EngineRequest(
        target=Target(
            original_url=url,
            canonical_url=url,
            target_key="tiktok:example",
            platform=Platform.TIKTOK,
            username="example",
            content_type=content_type,
        ),
        media=MediaKind.VIDEOS,
        destination=tmp_path / "downloads",
        url=url,
        auth=auth_spec or AuthSpec(AuthMode.NONE),
        archive=tmp_path / "archive.txt",
        user_agent="Nami Test Agent",
        timeout_seconds=90,
    )


def test_profile_batch_does_not_disable_playlists(tmp_path: Path) -> None:
    url = "https://www.tiktok.com/@example"
    spec = YtDlpEngine().build_command(request(tmp_path, content_type="profile", url=url))

    assert spec.argv == (
        sys.executable,
        "-m",
        "yt_dlp",
        "--output",
        str(tmp_path / "downloads" / "%(extractor)s" / "%(id)s.%(ext)s"),
        "--user-agent",
        "Nami Test Agent",
        "--download-archive",
        str(tmp_path / "archive.txt"),
        "--print",
        "after_move:filepath",
        url,
    )


def test_direct_content_adds_no_playlist_and_exact_cookie_args(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies file.txt"
    auth_spec = AuthSpec(AuthMode.COOKIE_FILE, cookie_file=cookie_file)
    url = "https://www.tiktok.com/@example/video/123?lang=en;echo-owned"

    spec = YtDlpEngine().build_command(request(tmp_path, content_type="video", url=url, auth_spec=auth_spec))

    assert spec.argv[-4:] == ("--no-playlist", "--cookies", str(cookie_file), url)
    assert spec.timeout_seconds == 90


def test_url_fallback_identifies_direct_content(tmp_path: Path) -> None:
    spec = YtDlpEngine().build_command(
        request(
            tmp_path,
            content_type="unknown",
            url="https://x.com/example/status/123?tracking=private",
        )
    )

    assert "--no-playlist" in spec.argv


def test_analyze_output_does_not_double_count_progress_lines() -> None:
    analysis = YtDlpEngine().analyze_output(
        [
            "[download] Destination: /downloads/video.f137.mp4",
            "[download] 100% of 10.00MiB in 00:01",
            '[Merger] Merging formats into "/downloads/video.mp4"',
            "/downloads/video.mp4",
            "/downloads/video.mp4",
            "[download] abc: has already been recorded in the archive",
            "[download] abc: has already been recorded in the archive",
        ]
    )

    assert analysis == (1, 1)
