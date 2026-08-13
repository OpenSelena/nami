"""Unit tests for TikTokAdapter platform adapter."""

from nami.auth import AuthConfig
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.platforms.tiktok import TikTokAdapter


class DummyManager:
    def download(self, target, content_type, destination, auth, progress_obj=None, active_task_id=None, context=None):
        return DownloadResult(
            status=DownloadResultStatus.SUCCESS,
            extractor="yt-dlp",
            message=f"downloaded {content_type}"
        )


def test_tiktok_adapter_routing(tmp_path):
    manager = DummyManager()
    adapter = TikTokAdapter(manager=manager)
    target = ParsedTarget("tiktok", "scout2015", "profile", "https://tiktok.com/@scout2015")
    auth = AuthConfig(mode="none")

    res_photos = adapter.download_photos(tmp_path, auth, target)
    res_videos = adapter.download_videos(tmp_path, auth, target)
    res_stories = adapter.download_stories(tmp_path, auth, target)
    res_hl = adapter.download_highlights(tmp_path, auth, target)

    assert res_photos.status == DownloadResultStatus.SUCCESS
    assert res_videos.status == DownloadResultStatus.SUCCESS
    assert res_stories.status == DownloadResultStatus.UNSUPPORTED
    assert res_hl.status == DownloadResultStatus.UNSUPPORTED
