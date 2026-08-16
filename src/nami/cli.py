"""Command-line and interactive entry points for Nami."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from nami import __version__
from nami.archive import (
    ArchiveError,
    ArchiveReset,
    discover_archives,
    reset_archives,
)
from nami.config import (
    DEFAULT_BROWSER,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    ConfigError,
    ConfigRepository,
    Settings,
    initialize_workspace,
    settings_for_root,
)
from nami.doctor import run_doctor
from nami.events import NullEventSink
from nami.models import MediaKind, Platform, Target
from nami.planner import DownloadRequest
from nami.service import create_default_service
from nami.targets import TargetParseError, load_profile_targets, parse_target

_CONFIG_KEYS = (
    "base_dir",
    "cookies_dir",
    "profiles_dir",
    "browser",
    "user_agent",
    "timeout_seconds",
)
_MENU_MEDIA = {
    "1": (MediaKind.PHOTOS,),
    "2": (MediaKind.VIDEOS,),
    "3": (MediaKind.STORIES,),
    "4": (MediaKind.HIGHLIGHTS,),
    "5": (MediaKind.PHOTOS, MediaKind.VIDEOS),
    "6": (MediaKind.STORIES, MediaKind.HIGHLIGHTS),
    "7": tuple(MediaKind),
}
_MEDIA_DIRECTORIES = {
    MediaKind.PHOTOS: "Photos",
    MediaKind.VIDEOS: "Videos",
    MediaKind.STORIES: "Stories",
    MediaKind.HIGHLIGHTS: "Highlights",
}
_SAFE_TARGET = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,239}\Z")


def build_parser() -> argparse.ArgumentParser:
    """Build Nami's side-effect-free argument parser."""
    parser = argparse.ArgumentParser(
        prog="nami",
        description="Download media from Instagram, TikTok, Facebook, and X.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("setup", help="initialize a Nami workspace")
    setup.add_argument("--root", type=Path, required=True, help="parent of the Nami directory")
    setup.add_argument(
        "--cookie-templates",
        action="store_true",
        help="create optional Netscape cookie templates",
    )
    setup.add_argument("--json", action="store_true", help="write one JSON result")
    setup.set_defaults(handler=_run_setup)

    download = commands.add_parser("download", help="download explicit or profile targets")
    download.add_argument("urls", nargs="*", metavar="URL")
    download.add_argument("--profiles", action="store_true", help="include configured profile files")
    download.add_argument("--platform", choices=[item.value for item in Platform])
    download.add_argument(
        "--media",
        type=_parse_media,
        default=tuple(MediaKind),
        metavar="KINDS",
        help="comma-separated photos,videos,stories,highlights or all",
    )
    download.add_argument("--json", action="store_true", help="write one JSON result")
    download.set_defaults(handler=_run_download)

    doctor = commands.add_parser("doctor", help="inspect local Nami dependencies and state")
    doctor.add_argument("--json", action="store_true", help="write one JSON report")
    doctor.set_defaults(handler=_run_doctor)

    config = commands.add_parser("config", help="show or edit configuration")
    _add_json_option(config)
    config_commands = config.add_subparsers(dest="config_command", required=True)
    show = config_commands.add_parser("show", help="show all settings")
    _add_json_option(show, suppress_default=True)
    show.set_defaults(handler=_run_config)
    get = config_commands.add_parser("get", help="show one setting")
    get.add_argument("key", choices=_CONFIG_KEYS)
    _add_json_option(get, suppress_default=True)
    get.set_defaults(handler=_run_config)
    set_command = config_commands.add_parser("set", help="persist one setting")
    set_command.add_argument("key", choices=_CONFIG_KEYS)
    set_command.add_argument("value")
    _add_json_option(set_command, suppress_default=True)
    set_command.set_defaults(handler=_run_config)
    unset = config_commands.add_parser("unset", help="reset one setting")
    unset.add_argument("key", choices=_CONFIG_KEYS)
    _add_json_option(unset, suppress_default=True)
    unset.set_defaults(handler=_run_config)

    archive = commands.add_parser("archive", help="manage download archives")
    archive_commands = archive.add_subparsers(dest="archive_command", required=True)
    reset = archive_commands.add_parser("reset", help="back up or delete archives")
    reset.add_argument("--platform", choices=[item.value for item in Platform])
    reset.add_argument("--target")
    reset.add_argument("--media", choices=[item.value for item in MediaKind])
    reset.add_argument("--all", dest="all_archives", action="store_true")
    reset.add_argument("--dry-run", action="store_true")
    reset.add_argument("--yes", action="store_true", help="confirm mutation")
    reset.add_argument(
        "--delete",
        action="store_true",
        help="permanently delete instead of backing up",
    )
    reset.add_argument("--json", action="store_true", help="write one JSON result")
    reset.set_defaults(handler=_run_archive_reset)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run Nami and return a deterministic process exit status."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return run_interactive()

    parser = build_parser()
    try:
        namespace = parser.parse_args(arguments)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)
    return int(namespace.handler(namespace))


def run_interactive(repository: ConfigRepository | None = None, console: Any | None = None) -> int:
    """Run the legacy no-argument menu over the current domain APIs."""
    from nami import ui

    repo = repository or ConfigRepository()
    output = console or ui.make_console()
    try:
        try:
            settings = repo.load()
        except ConfigError as error:
            warning = ui.Text("Configuration error: ", style="error")
            warning.append(str(error))
            output.print(warning)
            settings = settings_for_root(repo.home, config_file=repo.path)

        while True:
            configured = settings if ui.workspace_ready(settings) else None
            choice = ui.prompt_main_menu(output, configured, __version__)
            if choice == "0":
                output.print(ui.Text("Bye.", style="muted"))
                return 0
            if configured is None:
                try:
                    settings = ui.run_setup_prompt(repo, output)
                except ConfigError as error:
                    message = ui.Text("Setup failed: ", style="error")
                    message.append(str(error))
                    output.print(message)
                continue
            if choice == "8":
                settings = ui.run_settings_menu(repo, settings, output)
                continue

            targets, profile_errors = load_profile_targets(settings)
            if profile_errors:
                ui.render_profile_errors(profile_errors, output)
            if not targets:
                output.print(ui.Text(f"No valid profiles found under {settings.profiles_dir}", style="warning"))
                ui.pause(output)
                continue

            service = create_default_service(event_sink=ui.RichEventSink(output))
            request = DownloadRequest(tuple(targets), _MENU_MEDIA[choice], settings)
            batch = service.execute(request)
            ui.render_batch_result(batch, output)
            ui.pause(output)
    except ui.PromptCancelled as cancellation:
        output.print(ui.Text("Cancelled.", style="warning"))
        return cancellation.exit_code
    except KeyboardInterrupt:
        output.print(ui.Text("Cancelled.", style="warning"))
        return 130


def _run_setup(arguments: argparse.Namespace) -> int:
    repository = ConfigRepository()
    try:
        root = arguments.root.expanduser().resolve()
        if root.exists() and not root.is_dir():
            raise ConfigError(f"setup root is not a directory: {root}")
        settings = settings_for_root(root, config_file=repository.path)
        initialize_workspace(settings, create_cookie_templates=arguments.cookie_templates)
        repository.save(settings)
    except (ConfigError, OSError) as error:
        return _emit_error(str(error), json_mode=arguments.json)

    payload = _settings_payload(settings)
    payload["cookie_templates"] = bool(arguments.cookie_templates)
    if arguments.json:
        _write_json(payload)
    else:
        from nami.ui import make_console

        console = make_console()
        console.print("Nami workspace initialized")
        console.print(f"Downloads: {settings.base_dir}")
        console.print(f"Cookies: {settings.cookies_dir}")
        console.print(f"Profiles: {settings.profiles_dir}")
        console.print(f"Config: {repository.path}")
    return 0


def _run_download(arguments: argparse.Namespace) -> int:
    if not arguments.urls and not arguments.profiles:
        return _emit_error(
            "download requires at least one URL or --profiles",
            json_mode=arguments.json,
        )

    repository = ConfigRepository()
    try:
        settings = _load_configured_settings(repository, initialize=True)
    except ConfigError as error:
        return _emit_error(str(error), json_mode=arguments.json)

    platform = Platform(arguments.platform) if arguments.platform else None
    targets: list[Target] = []
    url_errors: list[dict[str, object]] = []
    for raw in arguments.urls:
        try:
            targets.append(parse_target(raw, platform))
        except TargetParseError as error:
            url_errors.append({"url": raw, "message": str(error)})
    if url_errors:
        if arguments.json:
            _write_json({"error": "invalid target URL", "target_errors": url_errors})
        else:
            for error in url_errors:
                print(
                    f"Target error: {error['url']}: {error['message']}",
                    file=sys.stderr,
                )
        return 2

    profile_errors: list[TargetParseError] = []
    if arguments.profiles:
        selected = None if platform is None else (platform,)
        loaded, profile_errors = load_profile_targets(settings, selected)
        targets.extend(loaded)

    targets = _deduplicate_targets(targets)
    serialized_profile_errors = [_profile_error_payload(error) for error in profile_errors]
    if not targets:
        payload: dict[str, object] = {
            "error": "no valid targets were found",
            "profile_errors": serialized_profile_errors,
        }
        if arguments.json:
            _write_json(payload)
        else:
            for error in profile_errors:
                _print_profile_error(error)
            print("Error: no valid targets were found", file=sys.stderr)
        return 2

    if profile_errors and not arguments.json:
        for error in profile_errors:
            _print_profile_error(error)

    if arguments.json:
        event_sink = NullEventSink()
    else:
        from nami.ui import RichEventSink, make_console

        event_sink = RichEventSink(make_console())

    service = create_default_service(event_sink=event_sink)
    request = DownloadRequest(tuple(targets), arguments.media, settings)
    try:
        batch = service.execute(request)
    except KeyboardInterrupt:
        if arguments.json:
            _write_json({"error": "download cancelled", "exit_code": 130})
        else:
            print("Download cancelled", file=sys.stderr)
        return 130

    exit_code = batch.exit_code()
    if arguments.json:
        payload = batch.to_dict()
        payload["profile_errors"] = serialized_profile_errors
        payload["exit_code"] = exit_code
        _write_json(payload)
    else:
        from nami.ui import make_console, render_batch_result

        render_batch_result(batch, make_console())
    return exit_code


def _run_doctor(arguments: argparse.Namespace) -> int:
    repository = ConfigRepository()
    config_error: ConfigError | None = None
    try:
        settings = repository.load()
    except ConfigError as error:
        config_error = error
        settings = settings_for_root(repository.home, config_file=repository.path)

    report = run_doctor(settings, config_error=config_error)
    if arguments.json:
        _write_json(report.to_dict())
    else:
        from nami.ui import make_console, render_doctor_report

        render_doctor_report(report, make_console())
    return report.exit_code()


def _run_config(arguments: argparse.Namespace) -> int:
    repository = ConfigRepository()
    try:
        settings = repository.load()
        action = arguments.config_command
        if action == "show":
            return _show_config(settings, json_mode=arguments.json)
        if action == "get":
            return _get_config(settings, arguments.key, json_mode=arguments.json)
        if action == "set":
            candidate = _replace_config_value(settings, arguments.key, arguments.value)
            repository.save(candidate)
            return _config_changed(
                arguments.key,
                getattr(candidate, arguments.key),
                reset=False,
                json_mode=arguments.json,
            )

        candidate = _unset_config_value(settings, arguments.key, repository.home)
        repository.save(candidate)
        return _config_changed(
            arguments.key,
            getattr(candidate, arguments.key),
            reset=True,
            json_mode=arguments.json,
        )
    except (ConfigError, OSError, ValueError) as error:
        return _emit_error(str(error), json_mode=arguments.json)


def _run_archive_reset(arguments: argparse.Namespace) -> int:
    if arguments.all_archives and any((arguments.platform, arguments.target, arguments.media)):
        return _emit_error(
            "--all cannot be combined with --platform, --target, or --media",
            json_mode=arguments.json,
        )
    if not arguments.all_archives and not any((arguments.platform, arguments.target, arguments.media)):
        return _emit_error(
            "archive reset requires a selector or explicit --all",
            json_mode=arguments.json,
        )
    if arguments.target and not _SAFE_TARGET.fullmatch(arguments.target):
        return _emit_error(
            "--target must be one safe target directory name",
            json_mode=arguments.json,
        )

    repository = ConfigRepository()
    try:
        settings = _load_configured_settings(repository, initialize=False)
        selected = _select_archives(
            settings.base_dir,
            platform=arguments.platform,
            target=arguments.target,
            media=arguments.media,
            all_archives=arguments.all_archives,
        )
        effective_dry_run = bool(arguments.dry_run or not arguments.yes)
        actions = _reset_selected_archives(
            settings.base_dir,
            selected,
            delete=arguments.delete,
            dry_run=effective_dry_run,
        )
    except (ArchiveError, ConfigError, OSError, ValueError) as error:
        return _emit_error(str(error), json_mode=arguments.json)

    payload = {
        "confirmed": bool(arguments.yes),
        "dry_run": effective_dry_run,
        "delete": bool(arguments.delete),
        "actions": [_archive_reset_payload(action) for action in actions],
    }
    if arguments.json:
        _write_json(payload)
    else:
        if not arguments.yes:
            print("Confirmation not supplied; reporting a dry run only.")
        if not actions:
            print("No matching archives found.")
        for action in actions:
            verb = "delete" if action.deleted else "back up"
            destination = "" if action.destination is None else f" -> {action.destination}"
            prefix = "Would" if action.dry_run else "Did"
            print(f"{prefix} {verb}: {action.source}{destination}")
    return 0


def _parse_media(value: str) -> tuple[MediaKind, ...]:
    raw = value.strip().lower()
    if raw == "all":
        return tuple(MediaKind)
    parts = raw.split(",")
    if not parts or any(not part or part != part.strip() for part in parts):
        raise argparse.ArgumentTypeError("media must be a comma-separated list without empty values")
    try:
        parsed = tuple(MediaKind(part) for part in parts)
    except ValueError as error:
        allowed = ",".join(item.value for item in MediaKind)
        raise argparse.ArgumentTypeError(f"media must contain only {allowed}, or all") from error
    if len(set(parsed)) != len(parsed):
        raise argparse.ArgumentTypeError("media values must not be repeated")
    return parsed


def _load_configured_settings(repository: ConfigRepository, *, initialize: bool) -> Settings:
    configured = repository.path.exists() or any(
        key in repository.environ
        for key in (
            "NAMI_BASE_DIR",
            "NAMI_COOKIES_DIR",
            "NAMI_PROFILES_DIR",
        )
    )
    if not configured:
        raise ConfigError("Nami is not configured; run 'nami setup --root PATH' first")
    settings = repository.load()
    if initialize:
        initialize_workspace(settings, create_cookie_templates=False)
    return settings


def _deduplicate_targets(targets: list[Target]) -> list[Target]:
    result: list[Target] = []
    seen: set[tuple[Platform, str]] = set()
    for target in targets:
        identity = (target.platform, target.canonical_url)
        if identity not in seen:
            seen.add(identity)
            result.append(target)
    return result


def _profile_error_payload(error: TargetParseError) -> dict[str, object]:
    return {
        "message": str(error),
        "source": None if error.source is None else str(error.source),
        "line_number": error.line_number,
        "raw": error.raw,
    }


def _print_profile_error(error: TargetParseError) -> None:
    location = ""
    if error.source is not None:
        location = str(error.source)
        if error.line_number is not None:
            location += f":{error.line_number}"
        location += ": "
    print(f"Profile error: {location}{error}", file=sys.stderr)


def _settings_payload(settings: Settings) -> dict[str, object]:
    return {
        "base_dir": str(settings.base_dir),
        "cookies_dir": str(settings.cookies_dir),
        "profiles_dir": str(settings.profiles_dir),
        "browser": settings.browser,
        "user_agent": settings.user_agent,
        "timeout_seconds": settings.timeout_seconds,
        "config_file": str(settings.config_file),
    }


def _show_config(settings: Settings, *, json_mode: bool) -> int:
    payload = _settings_payload(settings)
    if json_mode:
        _write_json(payload)
    else:
        from nami.ui import Text, make_console

        console = make_console()
        for key in _CONFIG_KEYS:
            line = Text(f"{key} = ")
            line.append(str(payload[key]))
            console.print(line)
    return 0


def _get_config(settings: Settings, key: str, *, json_mode: bool) -> int:
    value = getattr(settings, key)
    rendered = str(value)
    if json_mode:
        _write_json({"key": key, "value": value if isinstance(value, int) else rendered})
    else:
        print(rendered)
    return 0


def _replace_config_value(settings: Settings, key: str, raw: str) -> Settings:
    if key in {"base_dir", "cookies_dir", "profiles_dir"}:
        if not raw.strip():
            raise ConfigError(f"{key} must not be empty")
        value: object = Path(raw).expanduser().resolve()
    elif key == "timeout_seconds":
        try:
            value = int(raw)
        except ValueError as error:
            raise ConfigError("timeout_seconds must be an integer") from error
        if str(value) != raw.strip():
            raise ConfigError("timeout_seconds must be an integer")
    else:
        value = raw
    return replace(settings, **{key: value})


def _unset_config_value(settings: Settings, key: str, home: Path) -> Settings:
    defaults = settings_for_root(home, config_file=settings.config_file)
    values: dict[str, object] = {
        "base_dir": defaults.base_dir,
        "cookies_dir": settings.base_dir.parent / "cookies",
        "profiles_dir": settings.base_dir.parent / "profiles",
        "browser": DEFAULT_BROWSER,
        "user_agent": DEFAULT_USER_AGENT,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
    }
    return replace(settings, **{key: values[key]})


def _config_changed(key: str, value: object, *, reset: bool, json_mode: bool) -> int:
    rendered: object = value if isinstance(value, int) else str(value)
    if json_mode:
        _write_json({"key": key, "value": rendered, "reset": reset})
    elif reset:
        print(f"Reset {key} to its default/derived value: {rendered}")
    else:
        print(f"Set {key} to {rendered}")
    return 0


def _select_archives(
    base_dir: Path,
    *,
    platform: str | None,
    target: str | None,
    media: str | None,
    all_archives: bool,
) -> tuple[Path, ...]:
    archives = discover_archives(base_dir)
    if all_archives:
        return archives
    media_directory = None if media is None else _MEDIA_DIRECTORIES[MediaKind(media)]
    selected: list[Path] = []
    root = base_dir.expanduser().resolve()
    for archive in archives:
        parts = archive.parent.relative_to(root).parts
        if platform is not None and (not parts or parts[0] != platform):
            continue
        if target is not None and (len(parts) < 2 or parts[1] != target):
            continue
        if media_directory is not None and (len(parts) < 3 or parts[2] != media_directory):
            continue
        selected.append(archive)
    return tuple(selected)


def _reset_selected_archives(
    base_dir: Path,
    archives: tuple[Path, ...],
    *,
    delete: bool,
    dry_run: bool,
) -> tuple[ArchiveReset, ...]:
    root = base_dir.expanduser().resolve()
    actions: list[ArchiveReset] = []
    for archive in archives:
        selector = archive.parent.relative_to(root).as_posix()
        resets = reset_archives(
            root,
            selector,
            delete=delete,
            dry_run=dry_run,
        )
        for reset in resets:
            if reset.source == archive:
                actions.append(reset)
    return tuple(actions)


def _archive_reset_payload(action: ArchiveReset) -> dict[str, object]:
    return {
        "source": str(action.source),
        "destination": None if action.destination is None else str(action.destination),
        "deleted": action.deleted,
        "dry_run": action.dry_run,
    }


def _add_json_option(parser: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
    default: object = argparse.SUPPRESS if suppress_default else False
    parser.add_argument(
        "--json",
        action="store_true",
        default=default,
        help="write one JSON result",
    )


def _emit_error(message: str, *, json_mode: bool) -> int:
    if json_mode:
        _write_json({"error": message})
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 2


def _write_json(payload: object) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
