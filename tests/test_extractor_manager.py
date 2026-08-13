"""Unit tests for Nami ExtractorManager and capability registry."""

from nami.auth import AuthConfig
from nami.extractor_manager import EXTRACTOR_CAPABILITIES, ExtractorManager
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.retry import FailureType


def test_capability_registry_structure():
    assert "gallery-dl" in EXTRACTOR_CAPABILITIES
    assert "yt-dlp" in EXTRACTOR_CAPABILITIES
    assert "instaloader" not in EXTRACTOR_CAPABILITIES

    # Capabilities verification
    assert "instagram" in EXTRACTOR_CAPABILITIES["gallery-dl"]
    assert "tiktok" in EXTRACTOR_CAPABILITIES["gallery-dl"]
    assert "tiktok" in EXTRACTOR_CAPABILITIES["yt-dlp"]


def test_extractor_manager_plan_generation():
    manager = ExtractorManager()

    ig_profile_plan = manager.get_plan("instagram", "profile")
    assert ig_profile_plan == ["gallery-dl"]

    ig_photos_plan = manager.get_plan("instagram", "photos")
    assert ig_photos_plan == ["gallery-dl"]

    ig_story_plan = manager.get_plan("instagram", "story")
    assert ig_story_plan == ["gallery-dl"]

    ig_highlight_plan = manager.get_plan("instagram", "highlight")
    assert ig_highlight_plan == ["gallery-dl"]

    ig_video_plan = manager.get_plan("instagram", "videos")
    assert ig_video_plan == ["gallery-dl", "yt-dlp"]

    tiktok_plan = manager.get_plan("tiktok", "videos")
    assert tiktok_plan == ["yt-dlp", "gallery-dl"]

    fb_plan = manager.get_plan("facebook", "videos")
    assert fb_plan == ["yt-dlp", "gallery-dl"]

    x_plan = manager.get_plan("x", "videos")
    assert x_plan == ["yt-dlp", "gallery-dl"]


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
    target = ParsedTarget("instagram", "testuser", "videos", "https://instagram.com/testuser")
    auth = AuthConfig(mode="none")

    # Primary (gallery-dl) fails with EXTRACTOR failure
    class MockGalleryDlFail:
        name = "gallery-dl"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.FAILED, extractor="gallery-dl", failure_type=FailureType.EXTRACTOR)

    # Fallback (yt-dlp) succeeds
    class MockYtDlpSuccess:
        name = "yt-dlp"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.SUCCESS, extractor="yt-dlp")

    from nami.extractor_manager import EXTRACTORS
    monkeypatch.setitem(EXTRACTORS, "gallery-dl", MockGalleryDlFail())
    monkeypatch.setitem(EXTRACTORS, "yt-dlp", MockYtDlpSuccess())

    res = manager.download(target, "videos", tmp_path, auth)
    assert res.status == DownloadResultStatus.SUCCESS
    assert res.extractor == "yt-dlp"


def test_extractor_manager_no_fallback_on_unknown_failure(tmp_path, monkeypatch):
    manager = ExtractorManager()
    target = ParsedTarget("instagram", "testuser", "videos", "https://instagram.com/testuser")
    auth = AuthConfig(mode="none")

    # Primary (gallery-dl) fails with UNKNOWN failure
    class MockGalleryDlUnknownFail:
        name = "gallery-dl"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.FAILED, extractor="gallery-dl", failure_type=FailureType.UNKNOWN)

    class MockYtDlp:
        name = "yt-dlp"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.SUCCESS, extractor="yt-dlp")

    from nami.extractor_manager import EXTRACTORS
    monkeypatch.setitem(EXTRACTORS, "gallery-dl", MockGalleryDlUnknownFail())
    monkeypatch.setitem(EXTRACTORS, "yt-dlp", MockYtDlp())

    res = manager.download(target, "videos", tmp_path, auth)
    assert res.status == DownloadResultStatus.FAILED
    assert res.extractor == "gallery-dl"
    assert res.failure_type == FailureType.UNKNOWN


def test_extractor_manager_no_fallback_on_rate_limit(tmp_path, monkeypatch):
    manager = ExtractorManager()
    target = ParsedTarget("instagram", "testuser", "videos", "https://instagram.com/testuser")
    auth = AuthConfig(mode="none")

    # Primary (gallery-dl) fails with RATE_LIMIT
    class MockGalleryDlRateLimit:
        name = "gallery-dl"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.FAILED, extractor="gallery-dl", failure_type=FailureType.RATE_LIMIT)

    class MockYtDlp:
        name = "yt-dlp"
        def supports(self, p, c): return True
        def download(self, target, destination, auth, progress_obj=None, active_task_id=None, context=None):
            return DownloadResult(status=DownloadResultStatus.SUCCESS, extractor="yt-dlp")

    from nami.extractor_manager import EXTRACTORS
    monkeypatch.setitem(EXTRACTORS, "gallery-dl", MockGalleryDlRateLimit())
    monkeypatch.setitem(EXTRACTORS, "yt-dlp", MockYtDlp())

    res = manager.download(target, "videos", tmp_path, auth)
    assert res.status == DownloadResultStatus.FAILED
    assert res.extractor == "gallery-dl"
    assert res.failure_type == FailureType.RATE_LIMIT
