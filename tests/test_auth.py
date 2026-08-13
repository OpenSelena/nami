"""Unit tests for Nami authentication and cookie handling."""

from nami.auth import (
    validate_browser,
    validate_cookie,
    resolve_authentication,
    SUPPORTED_BROWSERS,
)


def test_supported_browsers():
    assert validate_browser("brave")
    assert validate_browser("chrome")
    assert validate_browser("edge")
    assert validate_browser("firefox")
    assert not validate_browser("foobar")
    assert not validate_browser("safari")


def test_validate_cookie_content(tmp_path):
    cookie_file = tmp_path / "test_cookie.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tFALSE\t1700000000\tsessionid\t12345\n")
    assert validate_cookie(cookie_file)

    bad_cookie = tmp_path / "bad.txt"
    bad_cookie.write_text("invalid content here")
    assert not validate_cookie(bad_cookie)


def test_resolve_auth_netscape(tmp_path):
    cookies_dir = tmp_path / "cookies"
    cookies_dir.mkdir()
    ig_cookie = cookies_dir / "instagram.com_cookies.txt"
    ig_cookie.write_text("# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tFALSE\t1700000000\tsessionid\t12345\n")

    auth = resolve_authentication("instagram", cookies_dir, "brave")
    assert auth.mode == "netscape"
    assert auth.path == ig_cookie
    assert auth.to_cli_args() == ["--cookies", str(ig_cookie)]


def test_resolve_auth_tiktok_browser_fallback(tmp_path):
    cookies_dir = tmp_path / "empty_cookies"
    cookies_dir.mkdir()
    auth = resolve_authentication("tiktok", cookies_dir, "firefox")
    assert auth.mode == "browser"
    assert auth.browser == "firefox"
    assert auth.to_cli_args() == ["--cookies-from-browser", "firefox"]
