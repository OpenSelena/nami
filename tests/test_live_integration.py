"""Optional live integration tests for Nami extractors.

Skipped by default to prevent CI failures due to external rate limits or network issues.
Enable by running: NAMI_LIVE_TESTS=1 pytest tests/test_live_integration.py
"""

import os
import pytest
from nami.auth import AuthConfig
from nami.extractors.gallery_dl import GalleryDlExtractor
from nami.extractors.instaloader import InstaloaderExtractor
from nami.extractors.yt_dlp import YtDlpExtractor
from nami.parser import ParsedTarget
from nami.platforms import DownloadResultStatus

pytestmark = pytest.mark.skipif(
    os.environ.get("NAMI_LIVE_TESTS") != "1",
    reason="Set NAMI_LIVE_TESTS=1 to run live network integration tests",
)


def test_live_instaloader_public_post(tmp_path):
    extractor = InstaloaderExtractor()
    target = ParsedTarget("instagram", "instagram", "post", "https://www.instagram.com/p/C_123456789/", content_id="C_123456789")
    auth = AuthConfig(mode="none")
    result = extractor.download(target, tmp_path, auth)
    assert result.extractor == "instaloader"
    assert result.status in (DownloadResultStatus.SUCCESS, DownloadResultStatus.FAILED)


def test_live_gallery_dl_public_url(tmp_path):
    extractor = GalleryDlExtractor()
    target = ParsedTarget("x", "x", "video", "https://x.com/x/status/123456789")
    auth = AuthConfig(mode="none")
    result = extractor.download(target, tmp_path, auth)
    assert result.extractor == "gallery-dl"
    assert result.status in (DownloadResultStatus.SUCCESS, DownloadResultStatus.FAILED)


def test_live_yt_dlp_public_url(tmp_path):
    extractor = YtDlpExtractor()
    target = ParsedTarget("tiktok", "tiktok", "video", "https://www.tiktok.com/@tiktok/video/123456789")
    auth = AuthConfig(mode="none")
    result = extractor.download(target, tmp_path, auth)
    assert result.extractor == "yt-dlp"
    assert result.status in (DownloadResultStatus.SUCCESS, DownloadResultStatus.FAILED)
