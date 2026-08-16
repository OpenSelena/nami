from __future__ import annotations

import os
from io import StringIO
from pathlib import Path

import pytest

from nami import cli, ui
from nami.config import (
    ConfigRepository,
    Settings,
    initialize_workspace,
    settings_for_root,
)
from nami.models import BatchResult, MediaKind


def prepared_repository(tmp_path: Path) -> tuple[ConfigRepository, Settings]:
    repository = ConfigRepository(tmp_path / ".nami" / "nami_config.json", home=tmp_path, environ={})
    settings = settings_for_root(tmp_path, config_file=repository.path)
    initialize_workspace(settings)
    (settings.profiles_dir / "x_profiles.txt").write_text("https://x.com/example\n", encoding="utf-8")
    repository.save(settings)
    return repository, settings


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("1", (MediaKind.PHOTOS,)),
        ("2", (MediaKind.VIDEOS,)),
        ("3", (MediaKind.STORIES,)),
        ("4", (MediaKind.HIGHLIGHTS,)),
        ("5", (MediaKind.PHOTOS, MediaKind.VIDEOS)),
        ("6", (MediaKind.STORIES, MediaKind.HIGHLIGHTS)),
        ("7", tuple(MediaKind)),
    ],
)
def test_interactive_menu_download_mapping_and_no_cwd_change(
    choice: str,
    expected: tuple[MediaKind, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _ = prepared_repository(tmp_path)
    choices = iter((choice, "0"))
    requests = []

    class FakeService:
        def execute(self, request: object) -> BatchResult:
            requests.append(request)
            return BatchResult()

    monkeypatch.setattr(ui, "prompt_main_menu", lambda *args: next(choices))
    monkeypatch.setattr(ui, "pause", lambda console: None)
    monkeypatch.setattr(cli, "create_default_service", lambda *, event_sink: FakeService())
    monkeypatch.setattr(
        os,
        "chdir",
        lambda path: pytest.fail(f"interactive mode changed cwd to {path}"),
    )
    original = Path.cwd()
    console = ui.make_console(file=StringIO(), environ={"NO_COLOR": "1"})

    assert cli.run_interactive(repository, console) == 0
    assert Path.cwd() == original
    assert len(requests) == 1
    assert requests[0].media == expected


def test_interactive_settings_mapping_uses_returned_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository, settings = prepared_repository(tmp_path)
    choices = iter(("8", "0"))
    calls = []
    changed = settings_for_root(tmp_path / "changed", config_file=repository.path, browser="firefox")
    initialize_workspace(changed)

    monkeypatch.setattr(ui, "prompt_main_menu", lambda *args: next(choices))

    def settings_menu(repo: object, current: Settings, console: object) -> Settings:
        del repo, console
        calls.append(current)
        return changed

    monkeypatch.setattr(ui, "run_settings_menu", settings_menu)
    console = ui.make_console(file=StringIO(), environ={"NO_COLOR": "1"})

    assert cli.run_interactive(repository, console) == 0
    assert calls == [settings]


def test_incomplete_workspace_offers_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = ConfigRepository(tmp_path / ".nami" / "nami_config.json", home=tmp_path, environ={})
    missing = settings_for_root(tmp_path, config_file=repository.path)
    repository.save(missing)
    ready = settings_for_root(tmp_path / "ready", config_file=repository.path)
    initialize_workspace(ready)
    presented = []
    choices = iter(("1", "0"))

    def menu(console: object, settings: Settings | None, version: str) -> str:
        del console, version
        presented.append(settings)
        return next(choices)

    monkeypatch.setattr(ui, "prompt_main_menu", menu)
    monkeypatch.setattr(ui, "run_setup_prompt", lambda repo, console: ready)
    console = ui.make_console(file=StringIO(), environ={"NO_COLOR": "1"})

    assert cli.run_interactive(repository, console) == 0
    assert presented[0] is None
    assert presented[1] == ready


def test_interactive_keyboard_cancel_has_no_traceback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository, _ = prepared_repository(tmp_path)

    def cancel(*args: object) -> str:
        del args
        raise ui.PromptCancelled(130)

    monkeypatch.setattr(ui, "prompt_main_menu", cancel)
    stream = StringIO()
    console = ui.make_console(file=stream, environ={"NO_COLOR": "1"})

    assert cli.run_interactive(repository, console) == 130
    assert "Cancelled" in stream.getvalue()
