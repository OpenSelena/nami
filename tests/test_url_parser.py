"""Unit tests for Nami URL and target parser."""

from nami.parser import parse_url, ParsedTarget


def test_parse_instagram_profile():
    res = parse_url("https://www.instagram.com/natgeo/", "instagram")
    assert isinstance(res, ParsedTarget)
    assert res.platform == "instagram"
    assert res.username == "natgeo"
    assert res.content_type == "profile"


def test_parse_instagram_reels_route():
    res = parse_url("https://instagram.com/natgeo/reels/", "instagram")
    assert isinstance(res, ParsedTarget)
    assert res.username == "natgeo"
    assert res.content_type == "reel"


def test_parse_instagram_stories_route():
    res = parse_url("https://instagram.com/stories/natgeo/", "instagram")
    assert isinstance(res, ParsedTarget)
    assert res.username == "natgeo"
    assert res.content_type == "story"


def test_parse_facebook_numeric_id():
    res = parse_url("https://www.facebook.com/profile.php?id=100064578912345", "facebook")
    assert isinstance(res, ParsedTarget)
    assert res.platform == "facebook"
    assert res.username == "100064578912345"
    assert res.content_type == "profile"


def test_parse_x_twitter_profile():
    res1 = parse_url("https://x.com/NASA", "x")
    res2 = parse_url("https://twitter.com/NASA", "x")
    assert isinstance(res1, ParsedTarget) and res1.username == "NASA"
    assert isinstance(res2, ParsedTarget) and res2.username == "NASA"


def test_parse_tiktok_profile():
    res = parse_url("https://www.tiktok.com/@scout2015", "tiktok")
    assert isinstance(res, ParsedTarget)
    assert res.platform == "tiktok"
    assert res.username == "scout2015"


def test_reject_invalid_domain():
    assert parse_url("https://malicious-site.com/user", "instagram") == "INVALID_URL"
    assert parse_url("https://instagram.com/user", "tiktok") == "INVALID_URL"


def test_reject_non_profile_routes():
    assert parse_url("https://instagram.com/explore/", "instagram") is None
    assert parse_url("https://instagram.com/p/", "instagram") is None


def test_parse_instagram_post_and_reel_urls():
    res_p = parse_url("https://www.instagram.com/p/C123456789/", "instagram")
    assert isinstance(res_p, ParsedTarget)
    assert res_p.content_type == "post"
    assert res_p.content_id == "C123456789"

    res_r = parse_url("https://www.instagram.com/reel/R987654321/", "instagram")
    assert isinstance(res_r, ParsedTarget)
    assert res_r.content_type == "reel"
    assert res_r.content_id == "R987654321"


def test_parse_tiktok_video_url():
    res = parse_url("https://www.tiktok.com/@scout2015/video/7123456789", "tiktok")
    assert isinstance(res, ParsedTarget)
    assert res.platform == "tiktok"
    assert res.username == "scout2015"
    assert res.content_type == "video"
    assert res.content_id == "7123456789"


def test_parse_x_status_url():
    res = parse_url("https://x.com/NASA/status/1234567890", "x")
    assert isinstance(res, ParsedTarget)
    assert res.platform == "x"
    assert res.username == "NASA"
    assert res.content_type == "video"
    assert res.content_id == "1234567890"
