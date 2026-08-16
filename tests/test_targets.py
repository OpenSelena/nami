from dataclasses import replace
from pathlib import Path

import pytest

from nami.config import initialize_workspace, settings_for_root
from nami.models import Platform
from nami.targets import (
    TargetParseError,
    load_profile_targets,
    parse_target,
    safe_target_dir,
)


@pytest.mark.parametrize(
    ("url", "platform", "username", "content_type", "content_id"),
    [
        ("HTTPS://WWW.INSTAGRAM.COM/NatGeo/?hl=en", Platform.INSTAGRAM, "NatGeo", "profile", None),
        ("https://instagram.com/p/C_abc-1/", Platform.INSTAGRAM, None, "post", "C_abc-1"),
        ("https://instagram.com/reel/R123/", Platform.INSTAGRAM, None, "reel", "R123"),
        ("https://instagram.com/stories/natgeo/123/", Platform.INSTAGRAM, "natgeo", "story", "123"),
        ("https://instagram.com/stories/highlights/987/", Platform.INSTAGRAM, None, "highlight", "987"),
        ("https://www.tiktok.com/@scout2015", Platform.TIKTOK, "scout2015", "profile", None),
        ("https://m.tiktok.com/@scout2015/video/7123456789", Platform.TIKTOK, "scout2015", "video", "7123456789"),
        ("https://fb.com/Meta", Platform.FACEBOOK, "Meta", "profile", None),
        (
            "https://m.facebook.com/profile.php?id=100064578912345",
            Platform.FACEBOOK,
            "100064578912345",
            "profile",
            None,
        ),
        ("https://facebook.com/Meta/posts/12345", Platform.FACEBOOK, "Meta", "post", "12345"),
        ("https://facebook.com/watch/?v=98765", Platform.FACEBOOK, None, "video", "98765"),
        ("https://twitter.com/NASA", Platform.X, "NASA", "profile", None),
        ("https://mobile.x.com/NASA/status/123456", Platform.X, "NASA", "post", "123456"),
    ],
)
def test_supported_url_examples(
    url: str,
    platform: Platform,
    username: str | None,
    content_type: str,
    content_id: str | None,
) -> None:
    target = parse_target(url)
    assert target.platform is platform
    assert target.username == username
    assert target.content_type == content_type
    assert target.content_id == content_id
    assert target.canonical_url.startswith("https://")


def test_current_profile_canonicalization_and_target_key() -> None:
    instagram = parse_target("https://m.instagram.com/NASA/?utm_source=test")
    twitter = parse_target("https://www.twitter.com/NASA/")
    facebook = parse_target("https://facebook.com/profile.php?id=123456&utm_source=test")
    assert instagram.canonical_url == "https://www.instagram.com/NASA/"
    assert instagram.target_key == "nasa"
    assert twitter.canonical_url == "https://x.com/NASA"
    assert facebook.canonical_url == "https://www.facebook.com/profile.php?id=123456"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://instagram.com/nasa",
        "https://evil.example/nasa",
        "https://instagram.com.evil.example/nasa",
        "https://vm.tiktok.com/abc123/",
        "https://vt.tiktok.com/abc123/",
        "https://instagram.com/explore/",
        "https://facebook.com/groups/example",
        "https://x.com/i/status/123",
        "https://tiktok.com/tag/cats",
        "https://instagram.com/../secret",
        "https://instagram.com/%2e%2e/secret",
        "https://instagram.com/foo%2fbar",
        "https://instagram.com/C:\\Windows\\System32",
        "https://instagram.com/..\\outside",
        "https://instagram.com/user\x00name",
    ],
)
def test_rejects_unsafe_or_non_profile_urls(url: str) -> None:
    with pytest.raises(TargetParseError):
        parse_target(url)


def test_platform_hint_rejects_mismatch_and_accepts_twitter_alias() -> None:
    with pytest.raises(TargetParseError, match="not tiktok"):
        parse_target("https://instagram.com/nasa", "tiktok")
    assert parse_target("https://twitter.com/NASA", "twitter").platform is Platform.X


def test_platform_specific_username_validation() -> None:
    with pytest.raises(TargetParseError):
        parse_target("https://x.com/this_name_is_far_too_long")
    with pytest.raises(TargetParseError):
        parse_target("https://instagram.com/name..name")
    with pytest.raises(TargetParseError):
        parse_target("https://tiktok.com/not-prefixed")


def test_safe_target_dir_proves_platform_containment(tmp_path: Path) -> None:
    target = parse_target("https://instagram.com/nasa")
    expected = (tmp_path / "instagram" / "nasa").resolve()
    assert safe_target_dir(tmp_path, target) == expected

    for unsafe in ("../outside", "..\\outside", "C:\\outside", "a/b", "\x00bad"):
        with pytest.raises(ValueError):
            safe_target_dir(tmp_path, replace(target, target_key=unsafe))


def test_safe_target_dir_rejects_platform_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    try:
        (tmp_path / "instagram").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(ValueError, match="escapes"):
        safe_target_dir(tmp_path, parse_target("https://instagram.com/nasa"))


def test_load_profile_targets_collects_errors_deduplicates_and_keeps_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_for_root(tmp_path)
    initialize_workspace(settings)
    profiles = settings.profiles_dir
    (profiles / "instagram_profiles.txt").write_text(
        "# profiles\nhttps://instagram.com/NASA\nhttps://m.instagram.com/NASA/\nhttps://evil.example/a\n",
        encoding="utf-8",
    )
    (profiles / "x_profiles.txt").write_text("https://twitter.com/OpenAI\n", encoding="utf-8")
    original_cwd = Path.cwd()
    monkeypatch.chdir(tmp_path / "Nami")
    changed_cwd = Path.cwd()

    targets, errors = load_profile_targets(settings, platforms=(Platform.INSTAGRAM, "x"))

    assert Path.cwd() == changed_cwd
    assert original_cwd != Path.cwd() or original_cwd == changed_cwd
    assert [target.username for target in targets] == ["NASA", "OpenAI"]
    assert len(errors) == 1
    assert errors[0].line_number == 4
    assert errors[0].source == profiles / "instagram_profiles.txt"
