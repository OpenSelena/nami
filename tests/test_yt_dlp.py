"""Unit tests for YtDlpExtractor engine."""

from nami.auth import AuthConfig
from nami.extractors.yt_dlp import YtDlpExtractor
from nami.parser import ParsedTarget
from nami.platforms import DownloadResultStatus


def test_yt_dlp_supports_video_platforms():
    extractor = YtDlpExtractor()
    assert extractor.supports("instagram", "post")
    assert extractor.supports("instagram", "reel")
    assert extractor.supports("tiktok", "video")
    assert extractor.supports("facebook", "video")
    assert extractor.supports("x", "video")


def test_yt_dlp_download_success(tmp_path, monkeypatch):
    extractor = YtDlpExtractor()
    target = ParsedTarget("tiktok", "testuser", "video", "https://tiktok.com/@testuser/video/123")
    auth = AuthConfig(mode="none")

    def mock_download_yt(*args, **kwargs):
        output = "[download] Destination: E:\\downloads\\testuser\\video.mp4\n[download] 100% of 1.2MiB\n"
        return 0, output, ""

    monkeypatch.setattr("nami.extractors.yt_dlp.download_yt", mock_download_yt)
    res = extractor.download(target, tmp_path, auth)
    assert res.status == DownloadResultStatus.SUCCESS
    assert res.extractor == "yt-dlp"
    assert res.items_downloaded >= 1
