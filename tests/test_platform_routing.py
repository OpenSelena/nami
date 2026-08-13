"""Unit tests for platform capability adapters and DownloadResult statuses."""

from nami.auth import AuthConfig
from nami.parser import ParsedTarget
from nami.platforms import DownloadResultStatus
from nami.platforms.tiktok import TikTokAdapter
from nami.platforms.facebook import FacebookAdapter
from nami.platforms.x import XAdapter


def test_unsupported_features_return_unsupported_status(tmp_path):
    target = ParsedTarget("tiktok", "scout2015", "profile", "https://tiktok.com/@scout2015")
    auth = AuthConfig(mode="none")
    adapter = TikTokAdapter()

    res_stories = adapter.download_stories(tmp_path, auth, target)
    res_highlights = adapter.download_highlights(tmp_path, auth, target)

    assert res_stories.status == DownloadResultStatus.UNSUPPORTED
    assert res_highlights.status == DownloadResultStatus.UNSUPPORTED
    assert res_stories.to_display_string() == "N/A"
    assert res_highlights.to_display_string() == "N/A"


def test_facebook_unsupported_stories(tmp_path):
    target = ParsedTarget("facebook", "user", "profile", "https://facebook.com/user")
    auth = AuthConfig(mode="none")
    adapter = FacebookAdapter()
    res = adapter.download_stories(tmp_path, auth, target)
    assert res.status == DownloadResultStatus.UNSUPPORTED


def test_x_unsupported_highlights(tmp_path):
    target = ParsedTarget("x", "user", "profile", "https://x.com/user")
    auth = AuthConfig(mode="none")
    adapter = XAdapter()
    res = adapter.download_highlights(tmp_path, auth, target)
    assert res.status == DownloadResultStatus.UNSUPPORTED
