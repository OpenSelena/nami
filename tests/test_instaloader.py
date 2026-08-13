"""Unit tests for InstaloaderExtractor engine."""

from nami.auth import AuthConfig
from nami.extractors.instaloader import InstaloaderExtractor
from nami.parser import ParsedTarget
from nami.platforms import DownloadResultStatus
from nami.retry import FailureType


def test_instaloader_supports_only_instagram():
    extractor = InstaloaderExtractor()
    assert extractor.supports("instagram", "profile")
    assert extractor.supports("instagram", "story")
    assert not extractor.supports("tiktok", "profile")
    assert not extractor.supports("facebook", "video")


def test_instaloader_rejects_non_instagram_download(tmp_path):
    extractor = InstaloaderExtractor()
    target = ParsedTarget("tiktok", "user", "profile", "https://tiktok.com/@user")
    auth = AuthConfig(mode="none")
    res = extractor.download(target, tmp_path, auth)
    assert res.status == DownloadResultStatus.UNSUPPORTED


def test_instaloader_exception_mapping(tmp_path, monkeypatch):
    extractor = InstaloaderExtractor()
    target = ParsedTarget("instagram", "user", "profile", "https://instagram.com/user")
    auth = AuthConfig(mode="none")

    # Mock _init_instaloader to raise LoginRequiredException
    def mock_init(*args, **kwargs):
        import instaloader.exceptions
        raise instaloader.exceptions.LoginRequiredException("Login required test")

    monkeypatch.setattr(extractor, "_init_instaloader", mock_init)
    res = extractor.download(target, tmp_path, auth)
    assert res.status == DownloadResultStatus.FAILED
    assert res.failure_type == FailureType.AUTH


def test_instaloader_too_many_requests_mapping(tmp_path, monkeypatch):
    extractor = InstaloaderExtractor()
    target = ParsedTarget("instagram", "user", "profile", "https://instagram.com/user")
    auth = AuthConfig(mode="none")

    def mock_init(*args, **kwargs):
        import instaloader.exceptions
        raise instaloader.exceptions.TooManyRequestsException("HTTP 429 Too Many Requests")

    monkeypatch.setattr(extractor, "_init_instaloader", mock_init)
    res = extractor.download(target, tmp_path, auth)
    assert res.status == DownloadResultStatus.FAILED
    assert res.failure_type == FailureType.RATE_LIMIT
