"""Unit tests for InstagramAdapter platform adapter."""

from nami.auth import AuthConfig
from nami.parser import ParsedTarget
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.platforms.instagram import InstagramAdapter
from nami.retry import FailureType


class DummyManager:
    def download(self, target, content_type, destination, auth, progress_obj=None, active_task_id=None, context=None):
        return DownloadResult(
            status=DownloadResultStatus.SUCCESS,
            extractor="gallery-dl",
            message=f"downloaded {content_type}"
        )


def test_instagram_adapter_routing(tmp_path):
    manager = DummyManager()
    adapter = InstagramAdapter(manager=manager)
    target = ParsedTarget("instagram", "natgeo", "profile", "https://instagram.com/natgeo")
    auth = AuthConfig(mode="none")

    res_photos = adapter.download_photos(tmp_path, auth, target)
    res_videos = adapter.download_videos(tmp_path, auth, target)
    res_stories = adapter.download_stories(tmp_path, auth, target)
    res_hl = adapter.download_highlights(tmp_path, auth, target)

    assert res_photos.status == DownloadResultStatus.SUCCESS
    assert res_videos.status == DownloadResultStatus.SUCCESS
    assert res_stories.status == DownloadResultStatus.SUCCESS
    assert res_hl.status == DownloadResultStatus.SUCCESS


def test_instagram_adapter_stories_requires_username(tmp_path):
    adapter = InstagramAdapter()
    target = ParsedTarget("instagram", None, "story", "https://instagram.com/stories/")
    auth = AuthConfig(mode="none")

    res = adapter.download_stories(tmp_path, auth, target)
    assert res.status == DownloadResultStatus.FAILED
    assert res.failure_type == FailureType.NOT_FOUND
