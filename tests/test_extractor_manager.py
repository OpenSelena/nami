"""Unit tests for Nami ExtractorManager and capability registry."""

from nami.auth import AuthConfig
from nami.extractor_manager import EXTRACTOR_CAPABILITIES, ExtractorManager
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.retry import FailureType


def test_capability_registry_structure():
    assert "instaloader" in EXTRACTOR_CAPABILITIES
    assert "gallery-dl" in EXTRACTOR_CAPABILITIES
    assert "yt-dlp" in EXTRACTOR_CAPABILITIES

    # Instaloader only supports instagram
    assert "instagram" in EXTRACTOR_CAPABILITIES["instaloader"]
    assert "tiktok" not in EXTRACTOR_CAPABILITIES["instaloader"]

    # TikTok does not support instaloader
    assert "tiktok" in EXTRACTOR_CAPABILITIES["yt-dlp"]
    assert "tiktok" in EXTRACTOR_CAPABILITIES["gallery-dl"]


def test_extractor_manager_plan_generation():
    manager = ExtractorManager()

    ig_profile_plan = manager.get_plan("instagram", "profile")
    assert ig_profile_plan[0] == "instaloader"

    ig_video_plan = manager.get_plan("instagram", "videos")
    assert "instaloader" in ig_video_plan
    assert "yt-dlp" in ig_video_plan

    tiktok_plan = manager.get_plan("tiktok", "videos")
    assert "yt-dlp" in tiktok_plan
    assert "instaloader" not in tiktok_plan

    fb_plan = manager.get_plan("facebook", "videos")
    assert "instaloader" not in fb_plan

    x_plan = manager.get_plan("x", "videos")
    assert "instaloader" not in x_plan


def test_fallback_allowed_rules():
    manager = ExtractorManager()

    assert not manager.is_fallback_allowed(FailureType.AUTH)
    assert not manager.is_fallback_allowed(FailureType.RATE_LIMIT)
    assert not manager.is_fallback_allowed(FailureType.NETWORK)
    assert not manager.is_fallback_allowed(FailureType.NOT_FOUND)
    assert not manager.is_fallback_allowed(FailureType.DEPENDENCY)

    assert manager.is_fallback_allowed(FailureType.EXTRACTOR)
    assert manager.is_fallback_allowed(None)


def test_extractor_manager_download_execution(tmp_path, monkeypatch):
    manager = ExtractorManager()
    target = ParsedTarget("tiktok", "user", "videos", "https://tiktok.com/@user")
    auth = AuthConfig(mode="none")

    # Mock success from yt-dlp
    class MockYtDlp:
        name = "yt-dlp"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.SUCCESS, extractor="yt-dlp")

    monkeypatch.setitem(
        __import__("nami.extractor_manager", fromlist=["EXTRACTORS"]).EXTRACTORS,
        "yt-dlp",
        MockYtDlp()
    )

    res = manager.download(target, "videos", tmp_path, auth)
    assert res.status == DownloadResultStatus.SUCCESS
    assert res.extractor == "yt-dlp"
