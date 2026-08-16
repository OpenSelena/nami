"""Rich presentation and interactive helpers for Nami."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

from nami.config import (
    ConfigError,
    ConfigRepository,
    Settings,
    initialize_workspace,
    settings_for_root,
)
from nami.doctor import CheckStatus, DoctorReport
from nami.events import DownloadEvent
from nami.models import BatchResult, Outcome
from nami.targets import TargetParseError

_DARK_STYLES = {
    "accent": "bold #D97757",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "muted": "dim",
}
_LIGHT_STYLES = {
    "accent": "bold #C45C2A",
    "success": "bold #1A7A3A",
    "warning": "bold #8A5A00",
    "error": "bold #B00020",
    "muted": "dim",
}


class PromptCancelled(Exception):
    """Raised when an interactive prompt is interrupted or reaches EOF."""

    def __init__(self, exit_code: int) -> None:
        super().__init__("interactive input cancelled")
        self.exit_code = exit_code


def detect_theme(environ: Mapping[str, str] | None = None) -> str:
    """Return the requested light/dark presentation theme."""
    env = os.environ if environ is None else environ
    explicit = env.get("NAMI_THEME", "auto").strip().lower()
    if explicit in {"light", "dark"}:
        return explicit
    colorfgbg = env.get("COLORFGBG", "")
    if colorfgbg:
        try:
            background = int(colorfgbg.rsplit(";", 1)[-1])
        except ValueError:
            pass
        else:
            if background in {7, 15}:
                return "light"
    return "dark"


def make_theme(environ: Mapping[str, str] | None = None) -> Theme:
    """Build Nami's Rich theme without reading configuration state."""
    styles = _LIGHT_STYLES if detect_theme(environ) == "light" else _DARK_STYLES
    return Theme(styles)


def make_console(
    *,
    file: TextIO | None = None,
    stderr: bool = False,
    environ: Mapping[str, str] | None = None,
) -> Console:
    """Construct a console honoring NO_COLOR and FORCE_COLOR."""
    env = os.environ if environ is None else environ
    no_color = bool(env.get("NO_COLOR"))
    force_value = env.get("FORCE_COLOR", "").strip().lower()
    force_color = force_value not in {"", "0", "false", "no"}
    return Console(
        file=file,
        stderr=stderr,
        theme=make_theme(env),
        force_terminal=False if no_color else (True if force_color else None),
        no_color=no_color,
        color_system=None if no_color else "auto",
        highlight=False,
        markup=False,
    )


class RichEventSink:
    """Render structured downloader events without interpreting remote markup."""

    def __init__(self, console: Console) -> None:
        self.console = console

    def emit(self, event: DownloadEvent) -> None:
        style = {
            "retry": "warning",
            "result": "accent",
            "output": "muted",
        }.get(event.kind, "accent")
        line = Text()
        if event.kind != "output":
            line.append(f"[{event.kind}] ", style=style)
        line.append(event.message, style="muted" if event.kind == "output" else None)
        self.console.print(line)


def render_batch_result(batch: BatchResult, console: Console) -> None:
    """Render operation outcomes and an aggregate status for people."""
    for result in batch.results:
        style = {
            Outcome.DOWNLOADED: "success",
            Outcome.UP_TO_DATE: "success",
            Outcome.NO_RESULTS: "warning",
            Outcome.UNSUPPORTED: "muted",
            Outcome.PARTIAL: "warning",
            Outcome.FAILED: "error",
            Outcome.CANCELLED: "warning",
            Outcome.INVALID: "error",
        }[result.outcome]
        line = Text()
        line.append(result.outcome.value.upper(), style=style)
        line.append("  ")
        line.append(f"{result.target.platform.value}/{result.target.target_key}/{result.media_kind.value}")
        if result.message:
            line.append(f" — {result.message}")
        console.print(line)

    exit_code = batch.exit_code()
    summary = Text()
    if not batch.results:
        summary.append("No download operations were needed", style="muted")
    elif exit_code == 0:
        summary.append("Downloads completed successfully", style="success")
    elif exit_code == 130:
        summary.append("Downloads cancelled", style="warning")
    elif any(result.outcome is Outcome.PARTIAL for result in batch.results):
        summary.append("Downloads completed partially", style="warning")
    elif any(result.outcome is Outcome.UNSUPPORTED for result in batch.results):
        summary.append("Downloads include unsupported operations", style="warning")
    else:
        summary.append("Downloads completed with failures", style="error")
    console.print(Panel(summary, box=box.ROUNDED, border_style="accent"))


def render_doctor_report(report: DoctorReport, console: Console) -> None:
    """Render a structured doctor report without Rich markup interpolation."""
    for check in report.checks:
        style = {
            CheckStatus.PASS: "success",
            CheckStatus.WARN: "warning",
            CheckStatus.FAIL: "error",
            CheckStatus.SKIP: "muted",
        }[check.status]
        line = Text()
        line.append(f"{check.status.value.upper():4}", style=style)
        line.append(f"  {check.name}: {check.message}")
        console.print(line)
        if check.remediation:
            remediation = Text("      ")
            remediation.append(check.remediation, style="muted")
            console.print(remediation)


def render_profile_errors(errors: list[TargetParseError], console: Console) -> None:
    """Render profile-file errors with literal paths and source lines."""
    for error in errors:
        location = ""
        if error.source is not None:
            location = str(error.source)
            if error.line_number is not None:
                location += f":{error.line_number}"
            location += ": "
        line = Text("PROFILE ERROR  ", style="error")
        line.append(f"{location}{error}")
        console.print(line)


def workspace_ready(settings: Settings) -> bool:
    """Return whether all configured workspace paths are directories."""
    try:
        return all(
            path.is_dir()
            for path in (
                settings.base_dir,
                settings.cookies_dir,
                settings.profiles_dir,
            )
        )
    except OSError:
        return False


def prompt_main_menu(console: Console, settings: Settings | None, version: str) -> str:
    """Display the configured menu, or offer setup for an incomplete workspace."""
    body = Text()
    if settings is None:
        body.append("Workspace setup is required.\n\n", style="warning")
        options = (("1", "Setup"), ("0", "Exit"))
        valid = {"0", "1"}
        default = "1"
    else:
        body.append("What do you want to download?\n\n")
        options = (
            ("1", "Photos only"),
            ("2", "Videos only"),
            ("3", "Stories only"),
            ("4", "Highlights only"),
            ("5", "Photos + Videos"),
            ("6", "Stories + Highlights"),
            ("7", "All"),
            ("8", "Settings"),
            ("0", "Exit"),
        )
        valid = {str(number) for number in range(9)}
        default = "7"
    for key, label in options:
        body.append(f" {key} ", style="accent")
        body.append(f"{label}\n")
    if settings is not None:
        body.append(f"\n Save: {settings.base_dir}", style="muted")
    panel = Panel(
        body,
        title=Text("Nami", style="accent"),
        subtitle=Text(f"v{version}", style="muted"),
        title_align="left",
        subtitle_align="right",
        border_style="accent",
        box=box.ROUNDED,
        padding=(1, 2),
        expand=False,
    )
    console.print(panel)
    return _prompt_choice(console, "> ", valid, default)


def run_setup_prompt(repository: ConfigRepository, console: Console) -> Settings:
    """Interactively initialize a workspace rooted below a chosen directory."""
    default_root = Path.cwd()
    intro = Text("Setup creates:\n\n")
    intro.append("  <path>/Nami/downloads\n")
    intro.append("  <path>/Nami/cookies\n")
    intro.append("  <path>/Nami/profiles\n\n")
    intro.append("Cookie templates are not created by default.", style="muted")
    console.print(Panel(intro, title=Text("Setup"), border_style="accent"))
    raw = _prompt_line(console, "Path", str(default_root)).strip().strip('"').strip("'")
    root = Path(raw or str(default_root)).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ConfigError(f"setup root is not a directory: {root}")

    settings = settings_for_root(root, config_file=repository.path)
    nami_root = settings.base_dir.parent
    if nami_root.exists():
        answer = _prompt_choice(console, f"Use existing {nami_root}? ", {"y", "n"}, "y")
        if answer != "y":
            raise PromptCancelled(0)

    initialize_workspace(settings, create_cookie_templates=False)
    repository.save(settings)
    summary = Text("Done\n\n", style="success")
    summary.append(f"  {settings.base_dir}\n")
    summary.append(f"  {settings.cookies_dir}\n")
    summary.append(f"  {settings.profiles_dir}\n")
    summary.append(f"  Config: {repository.path}", style="muted")
    console.print(Panel(summary, border_style="accent"))
    return settings


def run_settings_menu(repository: ConfigRepository, settings: Settings, console: Console) -> Settings:
    """Edit settings transactionally and return the last persisted value."""
    current = settings
    while True:
        body = Text()
        entries = (
            ("1", "Downloads", str(current.base_dir)),
            ("2", "Cookies", str(current.cookies_dir)),
            ("3", "Profiles", str(current.profiles_dir)),
            ("4", "Browser", current.browser),
            ("5", "Timeout seconds", str(current.timeout_seconds)),
            ("6", "Setup", ""),
            ("0", "Back", ""),
        )
        for key, label, value in entries:
            body.append(f" {key} ", style="accent")
            body.append(label)
            if value:
                body.append(f"\n     {value}", style="muted")
            body.append("\n")
        console.print(Panel(body, title=Text("Settings"), border_style="accent"))
        choice = _prompt_choice(console, "> ", {"0", "1", "2", "3", "4", "5", "6"}, "0")
        if choice == "0":
            return current
        if choice == "6":
            current = run_setup_prompt(repository, console)
            continue

        try:
            candidate = _settings_candidate(choice, current, console)
            if candidate == current:
                continue
            initialize_workspace(candidate, create_cookie_templates=False)
            repository.save(candidate)
        except (ConfigError, OSError, ValueError) as error:
            line = Text("Could not save setting: ", style="error")
            line.append(str(error))
            console.print(line)
            continue
        current = candidate
        console.print(Text("Saved", style="success"))


def pause(console: Console) -> None:
    """Wait for acknowledgement while treating EOF/interrupt as cancellation."""
    _ = _prompt_line(console, "Press Enter to continue", "")


def _settings_candidate(choice: str, settings: Settings, console: Console) -> Settings:
    if choice in {"1", "2", "3"}:
        field = {"1": "base_dir", "2": "cookies_dir", "3": "profiles_dir"}[choice]
        current = getattr(settings, field)
        raw = _prompt_line(console, field, str(current)).strip().strip('"').strip("'")
        value = current if not raw else Path(raw).expanduser().resolve()
        return replace(settings, **{field: value})
    if choice == "4":
        raw = _prompt_line(console, "Browser (brave/chrome/edge/firefox)", settings.browser)
        return replace(settings, browser=raw.strip() or settings.browser)
    raw = _prompt_line(console, "Timeout seconds", str(settings.timeout_seconds)).strip()
    try:
        timeout = settings.timeout_seconds if not raw else int(raw)
    except ValueError as error:
        raise ConfigError("timeout_seconds must be an integer") from error
    if raw and str(timeout) != raw:
        raise ConfigError("timeout_seconds must be an integer")
    return replace(settings, timeout_seconds=timeout)


def _prompt_choice(console: Console, label: str, choices: set[str], default: str) -> str:
    while True:
        value = _prompt_line(console, label, default).strip().lower() or default
        if value in choices:
            return value
        allowed = Text("Choose one of: ", style="warning")
        allowed.append(", ".join(sorted(choices)))
        console.print(allowed)


def _prompt_line(console: Console, label: str, default: str) -> str:
    prompt = Text(label, style="accent")
    if default:
        prompt.append(f" [{default}]", style="muted")
    prompt.append(": ")
    console.print(prompt, end="")
    try:
        return input()
    except EOFError as error:
        raise PromptCancelled(0) from error
    except KeyboardInterrupt as error:
        raise PromptCancelled(130) from error
