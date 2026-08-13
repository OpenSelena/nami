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
