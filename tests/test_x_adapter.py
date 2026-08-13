"""Unit tests for XAdapter platform adapter."""

from nami.auth import AuthConfig
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.platforms.x import XAdapter


class DummyManager:
    def download(self, target, content_type, destination, auth, progress_obj=None, active_task_id=None, context=None):
        return DownloadResult(
            status=DownloadResultStatus.SUCCESS,
            extractor="yt-dlp",
            message=f"downloaded {content_type}"
        )


def test_x_adapter_routing(tmp_path):
    manager = DummyManager()
    adapter = XAdapter(manager=manager)
    target = ParsedTarget("x", "NASA", "profile", "https://x.com/NASA")
    auth = AuthConfig(mode="none")

    res_photos = adapter.download_photos(tmp_path, auth, target)
    res_videos = adapter.download_videos(tmp_path, auth, target)
    res_hl = adapter.download_highlights(tmp_path, auth, target)

    assert res_photos.status == DownloadResultStatus.SUCCESS
    assert res_videos.status == DownloadResultStatus.SUCCESS
    assert res_hl.status == DownloadResultStatus.UNSUPPORTED
