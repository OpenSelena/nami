"""Unit tests for GalleryDlExtractor engine."""

from nami.auth import AuthConfig
from nami.extractors.gallery_dl import GalleryDlExtractor
from nami.parser import ParsedTarget
from nami.platforms import DownloadResultStatus


def test_gallery_dl_supports_all_platforms():
    extractor = GalleryDlExtractor()
    assert extractor.supports("instagram", "profile")
    assert extractor.supports("instagram", "photos")
    assert extractor.supports("instagram", "videos")
    assert extractor.supports("instagram", "story")
    assert extractor.supports("instagram", "highlight")
    assert extractor.supports("tiktok", "profile")
    assert extractor.supports("facebook", "video")
    assert extractor.supports("x", "photos")


def test_gallery_dl_download_success(tmp_path, monkeypatch):
    extractor = GalleryDlExtractor()
    target = ParsedTarget("instagram", "testuser", "profile", "https://instagram.com/testuser")
    auth = AuthConfig(mode="none")

    def mock_download_gd(*args, **kwargs):
        output = "E:\\downloads\\testuser\\1.jpg\nE:\\downloads\\testuser\\2.mp4\n"
        return 0, output, ""

    monkeypatch.setattr("nami.extractors.gallery_dl.download_gd", mock_download_gd)
    res = extractor.download(target, tmp_path, auth)
    assert res.status == DownloadResultStatus.SUCCESS
    assert res.extractor == "gallery-dl"
    assert res.items_downloaded == 2
