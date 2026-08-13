"""Pytest fixtures for Nami test suite."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from nami.config import Config


@pytest.fixture
def tmp_nami_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "Nami" / "downloads"
        cookies = Path(tmpdir) / "Nami" / "cookies"
        profiles = Path(tmpdir) / "Nami" / "profiles"
        base.mkdir(parents=True, exist_ok=True)
        cookies.mkdir(parents=True, exist_ok=True)
        profiles.mkdir(parents=True, exist_ok=True)
        yield base, cookies, profiles


@pytest.fixture
def mock_config(tmp_nami_dir):
    base, cookies, profiles = tmp_nami_dir
    cfg = Config()
    cfg.base_dir = base
    cfg.cookies_dir = cookies
    cfg.profiles_dir = profiles
    cfg.browser = "brave"
    yield cfg
