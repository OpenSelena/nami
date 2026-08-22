from __future__ import annotations

import json
from pathlib import Path

import pytest

from nami import cli
from nami.archive import archive_path
from nami.config import (
    ConfigRepository,
    Settings,
    initialize_workspace,
    settings_for_root,
)
from nami.models import BatchResult, MediaKind, OperationResult, Outcome
from nami.targets import parse_target


def use_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ConfigRepository:
    repository = ConfigRepository(tmp_path / ".nami" / "nami_config.json", home=tmp_path, environ={})
    monkeypatch.setattr(cli, "ConfigRepository", lambda: repository)
    return repository


def configured_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[ConfigRepository, Settings]:
    repository = use_repository(monkeypatch, tmp_path)
    settings = settings_for_root(tmp_path, config_file=repository.path)
    initialize_workspace(settings)
    repository.save(settings)
    return repository, settings


def result_batch(outcome: Outcome) -> BatchResult:
    target = parse_target("https://x.com/example")
    return BatchResult(
        (
            OperationResult(
                target=target,
                media_kind=MediaKind.PHOTOS,
                outcome=outcome,
            ),
        )
    )


def test_parser_exposes_commands_and_strict_media() -> None:
    parser = cli.build_parser()
    parsed = parser.parse_args(
        [
            "download",
            "https://x.com/example",
            "--platform",
            "x",
            "--media",
            "photos,videos",
        ]
    )
    assert parsed.command == "download"
    assert parsed.media == (MediaKind.PHOTOS, MediaKind.VIDEOS)
    assert parser.parse_args(["config", "--json", "show"]).json is True
    assert parser.parse_args(["config", "show", "--json"]).json is True

    with pytest.raises(SystemExit):
        parser.parse_args(["download", "https://x.com/example", "--media", "photos,bogus"])


def test_setup_initializes_and_atomically_saves_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = use_repository(monkeypatch, tmp_path)
    assert cli.main(["setup", "--root", str(tmp_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    settings = repository.load()
    assert payload["base_dir"] == str(settings.base_dir)
    assert settings.base_dir.is_dir()
    assert settings.profiles_dir.is_dir()
    assert not (settings.cookies_dir / "instagram_cookies.txt").exists()


def test_doctor_reports_malformed_config_as_one_json_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = use_repository(monkeypatch, tmp_path)
    repository.path.parent.mkdir(parents=True)
    repository.path.write_text("{bad json", encoding="utf-8")

    assert cli.main(["doctor", "--json"]) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    config = next(check for check in payload["checks"] if check["name"] == "config")
    assert config["status"] == "fail"
    assert "malformed JSON" in config["message"]
    assert captured.err == ""


def test_config_set_validation_and_unset_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository, _ = configured_repository(monkeypatch, tmp_path)

    assert cli.main(["config", "set", "browser", "firefox", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["value"] == "firefox"
    assert repository.load().browser == "firefox"

    assert cli.main(["config", "set", "timeout_seconds", "1.5", "--json"]) == 2
    assert "integer" in json.loads(capsys.readouterr().out)["error"]
    assert repository.load().timeout_seconds != 1

    assert cli.main(["config", "unset", "browser", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"key": "browser", "value": "brave", "reset": True}
    assert repository.load().browser == "brave"


def test_archive_requires_confirmation_and_honors_selectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, settings = configured_repository(monkeypatch, tmp_path)
    selected = archive_path(settings.base_dir / "instagram" / "nasa" / "Photos")
    other = archive_path(settings.base_dir / "x" / "nasa" / "Photos")
    for path in (selected, other):
        path.parent.mkdir(parents=True)
        path.write_text("entry\n", encoding="utf-8")

    assert cli.main(["archive", "reset", "--platform", "instagram", "--json"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] is True
    assert len(preview["actions"]) == 1
    assert selected.exists() and other.exists()

    assert (
        cli.main(
            [
                "archive",
                "reset",
                "--platform",
                "instagram",
                "--target",
                "nasa",
                "--media",
                "photos",
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    changed = json.loads(capsys.readouterr().out)
    assert changed["dry_run"] is False
    assert not selected.exists()
    assert selected.with_name("archive.txt.bak").exists()
    assert other.exists()

    assert cli.main(["archive", "reset", "--target", "../outside", "--json"]) == 2
    assert "safe" in json.loads(capsys.readouterr().out)["error"]


def test_download_json_is_stdout_only_and_returns_batch_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configured_repository(monkeypatch, tmp_path)
    batch = result_batch(Outcome.NO_RESULTS)

    class FakeService:
        def execute(self, request: object) -> BatchResult:
            del request
            return batch

    monkeypatch.setattr(cli, "create_default_service", lambda *, event_sink: FakeService())
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": pytest.fail(f"noninteractive command prompted: {prompt}"),
    )

    code = cli.main(["download", "https://x.com/example", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 4
    assert payload["exit_code"] == 4
    assert payload["results"][0]["outcome"] == "no_results"
    assert captured.err == ""


def test_download_profile_errors_are_in_json_without_prompting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, settings = configured_repository(monkeypatch, tmp_path)
    (settings.profiles_dir / "instagram_profiles.txt").write_text("https://evil.example/not-valid\n", encoding="utf-8")
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": pytest.fail(f"noninteractive command prompted: {prompt}"),
    )

    assert cli.main(["download", "--profiles", "--platform", "instagram", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile_errors"][0]["line_number"] == 1


def test_main_module_is_invokable(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr(cli, "main", lambda: 0)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("nami", run_name="__main__")
    assert exit_info.value.code == 0
