"""Unit tests for Nami configuration module."""

from nami.config import Config


def test_config_initial_state():
    cfg = Config()
    assert not cfg.is_configured()
    assert cfg.browser == "brave"


def test_config_ensure_dirs(tmp_nami_dir):
    base, cookies, profiles = tmp_nami_dir
    cfg = Config()
    cfg.base_dir = base
    cfg.cookies_dir = cookies
    cfg.profiles_dir = profiles
    assert cfg.is_configured()
    assert cfg.ensure_dirs()

    for p in ("instagram", "tiktok", "facebook", "x"):
        assert (profiles / f"{p}_profiles.txt").exists()
