"""Unit tests for FacebookAdapter platform adapter."""

from nami.auth import AuthConfig
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.platforms.facebook import FacebookAdapter


class DummyManager:
    def download(self, target, content_type, destination, auth, progress_obj=None, active_task_id=None, context=None):
        return DownloadResult(
            status=DownloadResultStatus.SUCCESS,
            extractor="yt-dlp",
            message=f"downloaded {content_type}"
        )


def test_facebook_adapter_routing(tmp_path):
    manager = DummyManager()
    adapter = FacebookAdapter(manager=manager)
    target = ParsedTarget("facebook", "user", "profile", "https://facebook.com/user")
    auth = AuthConfig(mode="none")

    res_photos = adapter.download_photos(tmp_path, auth, target)
    res_videos = adapter.download_videos(tmp_path, auth, target)
    res_stories = adapter.download_stories(tmp_path, auth, target)

    assert res_photos.status == DownloadResultStatus.SUCCESS
    assert res_videos.status == DownloadResultStatus.SUCCESS
    assert res_stories.status == DownloadResultStatus.UNSUPPORTED
