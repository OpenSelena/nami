import json
import os
from pathlib import Path

import pytest

from nami.config import (
    DEFAULT_TIMEOUT_SECONDS,
    ConfigError,
    ConfigRepository,
    initialize_workspace,
    settings_for_root,
)


def test_settings_for_root_builds_nami_layout(tmp_path: Path) -> None:
    settings = settings_for_root(tmp_path)
    assert settings.base_dir == tmp_path / "Nami" / "downloads"
    assert settings.cookies_dir == tmp_path / "Nami" / "cookies"
    assert settings.profiles_dir == tmp_path / "Nami" / "profiles"
    assert settings.timeout_seconds == DEFAULT_TIMEOUT_SECONDS


def test_environment_overrides_file_and_base_derives_siblings(tmp_path: Path) -> None:
    config_file = tmp_path / "config" / "nami.json"
    config_file.parent.mkdir()
    config_file.write_text(
        json.dumps(
            {
                "base_dir": str(tmp_path / "file" / "downloads"),
                "cookies_dir": str(tmp_path / "file" / "cookies"),
                "profiles_dir": str(tmp_path / "file" / "profiles"),
                "browser": "brave",
                "user_agent": "file-agent",
                "timeout_seconds": 10,
            }
        ),
        encoding="utf-8",
    )
    env_base = tmp_path / "env" / "downloads"
    repository = ConfigRepository(
        config_file,
        home=tmp_path,
        environ={
            "NAMI_BASE_DIR": str(env_base),
            "NAMI_BROWSER": "FIREFOX",
            "NAMI_USER_AGENT": "env-agent",
            "NAMI_TIMEOUT": "22",
        },
    )

    settings = repository.load()
    assert settings.base_dir == env_base
    assert settings.cookies_dir == env_base.parent / "cookies"
    assert settings.profiles_dir == env_base.parent / "profiles"
    assert settings.browser == "firefox"
    assert settings.user_agent == "env-agent"
    assert settings.timeout_seconds == 22


def test_individual_environment_paths_override_file(tmp_path: Path) -> None:
    config_file = tmp_path / "nami.json"
    config_file.write_text(
        json.dumps(
            {
                "base_dir": "file-downloads",
                "cookies_dir": "file-cookies",
                "profiles_dir": "file-profiles",
            }
        ),
        encoding="utf-8",
    )
    repository = ConfigRepository(
        config_file,
        home=tmp_path,
        environ={
            "NAMI_COOKIES_DIR": "env-cookies",
            "NAMI_PROFILES_DIR": "env-profiles",
        },
    )
    settings = repository.load()
    assert settings.base_dir == Path("file-downloads")
    assert settings.cookies_dir == Path("env-cookies")
    assert settings.profiles_dir == Path("env-profiles")


@pytest.mark.parametrize(
    "content",
    ["{not json", "[]", '{"browser": "safari"}', '{"timeout_seconds": 0}', '{"timeout_seconds": 86401}'],
)
def test_malformed_or_invalid_config_has_useful_error(tmp_path: Path, content: str) -> None:
    config_file = tmp_path / "nami.json"
    config_file.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        ConfigRepository(config_file, home=tmp_path, environ={}).load()
    assert str(error.value)


def test_invalid_environment_timeout_is_rejected(tmp_path: Path) -> None:
    repository = ConfigRepository(
        tmp_path / "nami.json",
        home=tmp_path,
        environ={"NAMI_TIMEOUT_SECONDS": "1.5"},
    )
    with pytest.raises(ConfigError, match="integer"):
        repository.load()


def test_initialize_workspace_is_non_destructive_and_secure(tmp_path: Path) -> None:
    settings = settings_for_root(tmp_path)
    initialize_workspace(settings)
    existing = settings.profiles_dir / "instagram_profiles.txt"
    existing.write_text("https://instagram.com/nasa\n", encoding="utf-8")
    initialize_workspace(settings, create_cookie_templates=True)

    assert existing.read_text(encoding="utf-8") == "https://instagram.com/nasa\n"
    for platform in ("instagram", "tiktok", "facebook", "x"):
        assert (settings.profiles_dir / f"{platform}_profiles.txt").is_file()
        cookie = settings.cookies_dir / f"{platform}_cookies.txt"
        assert cookie.read_text(encoding="utf-8").startswith("# Netscape HTTP Cookie File")
        if os.name != "nt":
            assert cookie.stat().st_mode & 0o777 == 0o600
    if os.name != "nt":
        assert settings.cookies_dir.stat().st_mode & 0o777 == 0o700
        assert settings.config_file.parent.stat().st_mode & 0o777 == 0o700


def test_save_is_atomic_and_round_trips(tmp_path: Path) -> None:
    config_file = tmp_path / ".nami" / "nami.json"
    repository = ConfigRepository(config_file, home=tmp_path, environ={})
    settings = settings_for_root(tmp_path, config_file=config_file, browser="edge")
    repository.save(settings)

    assert repository.load() == settings
    assert not list(config_file.parent.glob(f".{config_file.name}.*.tmp"))
    if os.name != "nt":
        assert config_file.stat().st_mode & 0o777 == 0o600


def test_failed_replace_preserves_old_config_and_cleans_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / ".nami" / "nami.json"
    config_file.parent.mkdir()
    original = '{"base_dir": "original"}\n'
    config_file.write_text(original, encoding="utf-8")
    repository = ConfigRepository(config_file, home=tmp_path, environ={})

    def fail_replace(source: Path | str, destination: Path | str) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("nami.config.os.replace", fail_replace)
    with pytest.raises(ConfigError, match="simulated replace failure"):
        repository.save(settings_for_root(tmp_path, config_file=config_file))

    assert config_file.read_text(encoding="utf-8") == original
    assert not list(config_file.parent.glob(f".{config_file.name}.*.tmp"))


def test_ensure_scripts_on_path_skips_when_already_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from nami.config import ensure_scripts_on_path, scripts_dir

    directory = scripts_dir()
    monkeypatch.setenv("PATH", directory + os.pathsep + "/other")
    assert ensure_scripts_on_path() is None


def test_ensure_scripts_on_path_adds_to_unix_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nami.config import ensure_scripts_on_path

    fake_scripts = str(tmp_path / "fake_scripts")
    monkeypatch.setattr("nami.config.scripts_dir", lambda: fake_scripts)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr("nami.config.sys.platform", "linux")
    monkeypatch.setattr("nami.config.Path.home", lambda: tmp_path)

    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("# existing\n", encoding="utf-8")
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("# existing\n", encoding="utf-8")

    result = ensure_scripts_on_path()

    assert result == fake_scripts
    assert fake_scripts in bashrc.read_text(encoding="utf-8")
    assert fake_scripts in zshrc.read_text(encoding="utf-8")
    assert not (tmp_path / ".profile").exists()


def test_ensure_scripts_on_path_is_idempotent_on_unix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nami.config import _add_to_unix_profiles

    fake_scripts = str(tmp_path / "fake_scripts")
    monkeypatch.setattr("nami.config.Path.home", lambda: tmp_path)

    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("# existing\n", encoding="utf-8")

    _add_to_unix_profiles(fake_scripts)
    first = bashrc.read_text(encoding="utf-8")
    _add_to_unix_profiles(fake_scripts)
    second = bashrc.read_text(encoding="utf-8")

    assert first == second
