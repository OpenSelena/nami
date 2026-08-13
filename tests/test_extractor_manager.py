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

    # Non-fallback eligible failure classes
    assert not manager.is_fallback_allowed(FailureType.AUTH)
    assert not manager.is_fallback_allowed(FailureType.RATE_LIMIT)
    assert not manager.is_fallback_allowed(FailureType.NETWORK)
    assert not manager.is_fallback_allowed(FailureType.NOT_FOUND)
    assert not manager.is_fallback_allowed(FailureType.DEPENDENCY)
    assert not manager.is_fallback_allowed(FailureType.UNKNOWN)
    assert not manager.is_fallback_allowed(FailureType.TIMEOUT)

    # Fallback eligible failure classes
    assert manager.is_fallback_allowed(FailureType.EXTRACTOR)
    assert manager.is_fallback_allowed(None)


def test_extractor_manager_fallback_on_extractor_failure(tmp_path, monkeypatch):
    manager = ExtractorManager()
    target = ParsedTarget("instagram", "testuser", "profile", "https://instagram.com/testuser")
    auth = AuthConfig(mode="none")

    # Primary fails with EXTRACTOR failure
    class MockInstaloaderFail:
        name = "instaloader"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.FAILED, extractor="instaloader", failure_type=FailureType.EXTRACTOR)

    # Fallback succeeds
    class MockGalleryDlSuccess:
        name = "gallery-dl"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.SUCCESS, extractor="gallery-dl")

    from nami.extractor_manager import EXTRACTORS
    monkeypatch.setitem(EXTRACTORS, "instaloader", MockInstaloaderFail())
    monkeypatch.setitem(EXTRACTORS, "gallery-dl", MockGalleryDlSuccess())

    res = manager.download(target, "profile", tmp_path, auth)
    assert res.status == DownloadResultStatus.SUCCESS
    assert res.extractor == "gallery-dl"


def test_extractor_manager_no_fallback_on_unknown_failure(tmp_path, monkeypatch):
    manager = ExtractorManager()
    target = ParsedTarget("instagram", "testuser", "profile", "https://instagram.com/testuser")
    auth = AuthConfig(mode="none")

    # Primary fails with UNKNOWN failure
    class MockInstaloaderUnknownFail:
        name = "instaloader"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.FAILED, extractor="instaloader", failure_type=FailureType.UNKNOWN)

    class MockGalleryDl:
        name = "gallery-dl"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.SUCCESS, extractor="gallery-dl")

    from nami.extractor_manager import EXTRACTORS
    monkeypatch.setitem(EXTRACTORS, "instaloader", MockInstaloaderUnknownFail())
    monkeypatch.setitem(EXTRACTORS, "gallery-dl", MockGalleryDl())

    res = manager.download(target, "profile", tmp_path, auth)
    assert res.status == DownloadResultStatus.FAILED
    assert res.extractor == "instaloader"
    assert res.failure_type == FailureType.UNKNOWN
