#!/usr/bin/env python3
"""
Nami — Multi-platform media downloader CLI engine.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    from importlib.metadata import version as pkg_version
    __version__ = pkg_version("nami")
except Exception:
    __version__ = "2.3.9"

from rich.align import Align
from rich.box import ROUNDED
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from nami.auth import SUPPORTED_BROWSERS, resolve_authentication, validate_browser
from nami.config import PLATFORMS, config
from nami.diagnostics import check_environment_health
from nami.parser import ParsedTarget, parse_url
from nami.platforms import DownloadResult, DownloadResultStatus
from nami.platforms.facebook import FacebookAdapter
from nami.platforms.instagram import InstagramAdapter
from nami.platforms.tiktok import TikTokAdapter
from nami.platforms.x import XAdapter
from nami.ui import C, clear_screen, console, make_progress, print_summary_table

ADAPTERS = {
    "instagram": InstagramAdapter(),
    "tiktok": TikTokAdapter(),
    "facebook": FacebookAdapter(),
    "x": XAdapter(),
}


def log_debug(context: str, exc: Exception) -> None:
    if config.debug_log is None:
        return
    try:
        config.debug_log.parent.mkdir(parents=True, exist_ok=True)
        with open(config.debug_log, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {context}: {exc!r}\n")
    except Exception:
        pass


def check_environment() -> None:
    if os.environ.get("NAMI_SKIP_ENV_CHECK") == "1":
        return

    health = check_environment_health()
    missing = health.get("missing_dependencies", [])
    if missing:
        console.print(Panel.fit(
            f"[{C['error']}]Missing required package(s): {', '.join(missing)}[/{C['error']}]\n"
            f"[{C['secondary']}]Install with:[/{C['secondary']}] "
            f"[bold]{sys.executable} -m pip install {' '.join(missing)}[/bold]",
            border_style="red",
            title=f"[{C['error']}]Environment Check Failed[/{C['error']}]"
        ))
        input("\nPress Enter to exit...")
        sys.exit(1)

    if health.get("urllib3_hijacked"):
        console.print(Panel.fit(
            f"[{C['warning']}]urllib3 namespace conflict detected.[/{C['warning']}]\n"
            f"[{C['secondary']}]{health.get('urllib3_detail')}[/{C['secondary']}]\n"
            f"[{C['secondary']}]Recommended action:[/{C['secondary']}]\n"
            f"[bold]{sys.executable} -m pip install -U nami gallery-dl yt-dlp urllib3[/bold]",
            border_style="yellow",
            title=f"[{C['warning']}]Dependency Diagnostic Warning[/{C['warning']}]"
        ))
        time.sleep(2)


def run_setup() -> bool:
    clear_screen()
    intro = Text()
    intro.append("Creates:\n\n", style=C["primary"])
    intro.append("  <path>/Nami/downloads\n", style=C["secondary"])
    intro.append("  <path>/Nami/cookies\n", style=C["secondary"])
    intro.append("  <path>/Nami/profiles\n\n", style=C["secondary"])
    intro.append("Enter parent path (Enter = current directory)", style=C["muted"])

    console.print(Panel(
        intro,
        title=f"[{C['muted']}]Setup[/{C['muted']}]",
        border_style=C["panel_border"],
        box=ROUNDED,
        padding=(1, 2),
        expand=False
    ))
    console.print()

    default_dir = Path.cwd()
    raw = Prompt.ask(
        f"[{C['accent_b']}]Path[/{C['accent_b']}]",
        default=str(default_dir),
        console=console
    )
    raw = raw.strip().strip('"').strip("'")
    if not raw:
        raw = str(default_dir)

    try:
        parent = Path(raw).expanduser().resolve()
    except Exception as e:
        console.print(f"[{C['error']}]Invalid path: {e}[/{C['error']}]")
        input("\nPress Enter...")
        return False

    if parent.exists() and not parent.is_dir():
        console.print(f"[{C['error']}]Not a directory.[/{C['error']}]")
        input("\nPress Enter...")
        return False

    nami_root = parent / "Nami"
    downloads = nami_root / "downloads"
    cookies = nami_root / "cookies"
    profiles = nami_root / "profiles"

    if nami_root.exists():
        console.print(f"[{C['warning']}]Exists: {nami_root}[/{C['warning']}]")
        confirm = Prompt.ask(
            f"[{C['accent_b']}]Use it? (y/n)[/{C['accent_b']}]",
            choices=["y", "n", "Y", "N"],
            default="y",
            console=console
        ).strip().lower()
        if confirm != "y":
            console.print(f"[{C['muted']}]Cancelled.[/{C['muted']}]")
            input("\nPress Enter...")
            return False

    config.base_dir = downloads
    config.cookies_dir = cookies
    config.profiles_dir = profiles
    config.debug_log = config.base_dir / "nami_debug.log"

    if not config.ensure_dirs() or not config.save():
        input("\nPress Enter...")
        return False

    clear_screen()
    summary = Text()
    summary.append("Done\n\n", style=C["success"])
    summary.append(f"  {downloads}\n", style=C["secondary"])
    summary.append(f"  {cookies}\n", style=C["secondary"])
    summary.append(f"  {profiles}\n", style=C["secondary"])

    console.print(Panel(
        summary,
        border_style=C["panel_border"],
        box=ROUNDED,
        padding=(1, 2),
        expand=False
    ))
    input("\nPress Enter...")
    return True


def _prompt_path(label: str, current: Path | None) -> Path | None:
    console.print(f"\n[{C['secondary']}]{label}[/{C['secondary']}]")
    console.print(f"[{C['muted']}]Current: {current}[/{C['muted']}]")
    console.print(
        f"[{C['muted']}]Enter a new path, or press Enter to keep the current value."
        f"[/{C['muted']}]"
    )
    raw = Prompt.ask(f"[{C['accent_b']}]>[/{C['accent_b']}]", default="", console=console)
    raw = raw.strip().strip('"').strip("'")
    if not raw:
        return current
    try:
        new_path = Path(raw).expanduser().resolve()
        new_path.mkdir(parents=True, exist_ok=True)
        return new_path
    except Exception as e:
        console.print(f"[{C['error']}]Invalid directory path: {e}[/{C['error']}]")
        return None


def settings_menu() -> None:
    if not config.is_configured():
        console.print(f"[{C['warning']}]Run Setup first.[/{C['warning']}]")
        input("\nPress Enter...")
        return

    while True:
        clear_screen()
        body = Text()
        body.append("  1  ", style=C["accent_b"])
        body.append("Save directory\n", style=C["secondary"])
        body.append(f"     {config.base_dir}\n\n", style=C["muted"])
        body.append("  2  ", style=C["accent_b"])
        body.append("Cookies directory\n", style=C["secondary"])
        body.append(f"     {config.cookies_dir}\n\n", style=C["muted"])
        body.append("  3  ", style=C["accent_b"])
        body.append("Browser\n", style=C["secondary"])
        body.append(f"     {config.browser}\n\n", style=C["muted"])
        body.append("  4  ", style=C["accent_b"])
        body.append("Setup\n", style=C["secondary"])
        body.append("  5  ", style=C["accent_b"])
        body.append("Back\n", style=C["secondary"])

        console.print(Align.center(Panel(
            body,
            title=f"[{C['muted']}]Settings[/{C['muted']}]",
            border_style=C["panel_border"],
            box=ROUNDED,
            padding=(1, 2),
            expand=False
        )))
        console.print()

        choice = Prompt.ask(
            f"[{C['accent_b']}]>[/{C['accent_b']}]",
            choices=["1", "2", "3", "4", "5"],
            default="5",
            show_choices=False,
            show_default=False,
            console=console
        ).strip()

        if choice == "1":
            new_path = _prompt_path("Save directory", config.base_dir)
            if new_path is not None and new_path != config.base_dir:
                config.base_dir = new_path
                config.debug_log = config.base_dir / "nami_debug.log"
                if config.save():
                    console.print(f"[{C['success']}]Saved.[/{C['success']}]")
                    config.ensure_dirs()

        elif choice == "2":
            new_path = _prompt_path("Cookies directory", config.cookies_dir)
            if new_path is not None and new_path != config.cookies_dir:
                config.cookies_dir = new_path
                if config.save():
                    console.print(f"[{C['success']}]Saved.[/{C['success']}]")
                    config.ensure_dirs()

        elif choice == "3":
            console.print(f"[{C['muted']}]Select supported browser: {', '.join(sorted(SUPPORTED_BROWSERS))}[/{C['muted']}]")
            raw = Prompt.ask(
                f"[{C['accent_b']}]>[/{C['accent_b']}]",
                choices=sorted(list(SUPPORTED_BROWSERS)),
                default=config.browser,
                console=console
            ).strip().lower()
            if raw and raw != config.browser and validate_browser(raw):
                config.browser = raw
                if config.save():
                    console.print(f"[{C['success']}]Saved browser setting.[/{C['success']}]")

        elif choice == "4":
            run_setup()

        elif choice == "5":
            return


def run_downloads(choice: str) -> None:
    if not config.is_configured():
        console.print(f"[{C['warning']}]Run Setup first.[/{C['warning']}]")
        input("\nPress Enter...")
        return

    if not config.ensure_dirs() or config.base_dir is None or config.profiles_dir is None:
        input("\nPress Enter to continue...")
        return

    original_cwd = Path.cwd()
    try:
        os.chdir(config.base_dir)
    except OSError as e:
        console.print(f"[{C['error']}][ERROR] Cannot change directory: {e}[/{C['error']}]")
        input("\nPress Enter to continue...")
        return

    targets_to_process: list[tuple[str, ParsedTarget]] = []
    for plat in PLATFORMS:
        profile_file = config.profiles_dir / f"{plat}_profiles.txt"
        if not profile_file.exists():
            continue
        try:
            with open(profile_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_stripped = line.strip()
                    if not line_stripped or line_stripped.startswith("#") or line_stripped.startswith(";"):
                        continue
                    parsed = parse_url(line_stripped, plat)
                    if isinstance(parsed, ParsedTarget):
                        targets_to_process.append((plat, parsed))
                    elif parsed == "INVALID_URL":
                        console.print(f"[{C['warning']}]-> [SKIP] Invalid platform URL: {line_stripped}[/{C['warning']}]")
                    else:
                        console.print(f"[{C['warning']}]-> [SKIP] Could not parse username from: {line_stripped}[/{C['warning']}]")
        except OSError as e:
            console.print(f"[{C['error']}][ERROR] Cannot read {profile_file.name}: {e}[/{C['error']}]")

    if not targets_to_process:
        console.print(f"[{C['warning']}]No valid profiles found under:[/{C['warning']}]")
        console.print(f"  [{C['muted']}]{config.profiles_dir}[/{C['muted']}]")
        input("\nPress Enter to continue...")
        return

    progress = make_progress()
    overall_task = progress.add_task(
        f"[{C['primary']}]Overall Progress[/{C['primary']}]",
        total=len(targets_to_process), status=""
    )
    active_task = progress.add_task(
        f"[{C['primary']}]Active Download[/{C['primary']}]",
        total=None, status="Waiting...", visible=False
    )

    header_printed: set[str] = set()
    summary_records: list[dict[str, str]] = []

    try:
        with progress:
            for plat, target in targets_to_process:
                if plat not in header_printed:
                    header = "X/TWITTER" if plat == "x" else plat.upper()
                    progress.console.print(f"\n[{C['accent_b']}]# {header}[/{C['accent_b']}]")
                    header_printed.add(plat)

                target_name = target.username or "target"
                progress.console.print(f" [{C['primary']}]-> {target_name}[/{C['primary']}]")
                progress.update(
                    active_task,
                    description=f"[{C['primary']}]{plat.upper()}: {target_name}[/{C['primary']}]",
                    completed=0, total=None, status="Initializing...", visible=True
                )

                adapter = ADAPTERS[plat]
                auth_config = resolve_authentication(plat, config.cookies_dir, config.browser)
                target_dir = config.base_dir / plat / target_name

                photos_res = DownloadResult(status=DownloadResultStatus.SKIPPED)
                videos_res = DownloadResult(status=DownloadResultStatus.SKIPPED)
                stories_res = DownloadResult(status=DownloadResultStatus.SKIPPED)
                highlights_res = DownloadResult(status=DownloadResultStatus.SKIPPED)

                # Execute requested download modes
                if choice in ("1", "5", "7"):
                    photos_res = adapter.download_photos(target_dir, auth_config, target, progress, active_task)
                if choice in ("2", "5", "7"):
                    videos_res = adapter.download_videos(target_dir, auth_config, target, progress, active_task)
                if choice in ("3", "6", "7"):
                    stories_res = adapter.download_stories(target_dir, auth_config, target, progress, active_task)
                if choice in ("4", "6", "7"):
                    highlights_res = adapter.download_highlights(target_dir, auth_config, target, progress, active_task)

                summary_records.append({
                    "platform": plat,
                    "username": target_name,
                    "photos": photos_res.to_display_string(),
                    "videos": videos_res.to_display_string(),
                    "stories": stories_res.to_display_string(),
                    "highlights": highlights_res.to_display_string(),
                })

                progress.advance(overall_task, 1)
                progress.update(active_task, visible=False)

            progress.update(overall_task, status=f"[{C['accent_b']}]Complete![/{C['accent_b']}]")
    except KeyboardInterrupt:
        console.print(f"\n[{C['error']}][INFO] Cancelled by user.[/{C['error']}]")
        return
    finally:
        try:
            os.chdir(original_cwd)
        except Exception:
            pass

    print_summary_table(summary_records)
    input("\nPress Enter to continue...")


def show_main_menu() -> str:
    clear_screen()
    configured = config.is_configured()
    menu_text = Text()

    if not configured:
        options = [("1", "Setup"), ("0", "Exit")]
        choices = ["0", "1"]
        default = "1"
    else:
        menu_text.append("What do you want to download?\n\n", style=C["primary"])
        options = [
            ("1", "Photos only"),
            ("2", "Videos only"),
            ("3", "Stories only"),
            ("4", "Highlights only"),
            ("5", "Photos + Videos"),
            ("6", "Stories + Highlights"),
            ("7", "All"),
            ("8", "Settings"),
            ("0", "Exit"),
        ]
        choices = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]
        default = "7"

    for key, label in options:
        menu_text.append(f" {key}", style=C["accent_b"])
        menu_text.append(" ")
        menu_text.append(f"{label}\n", style=C["secondary"])

    if configured and config.base_dir is not None:
        menu_text.append(f"\n Save: {config.base_dir}", style=C["muted"])

    console.print(Align.center(Panel(
        menu_text,
        title=f"[{C['muted']}]* Nami[/{C['muted']}]",
        subtitle=f"[{C['muted']}]v{__version__}[/{C['muted']}]",
        title_align="left",
        subtitle_align="right",
        border_style=C["panel_border"],
        box=ROUNDED,
        padding=(1, 2),
        expand=False
    )))
    console.print()

    return Prompt.ask(
        f"[{C['accent_b']}]>[/{C['accent_b']}]",
        choices=choices,
        default=default,
        show_choices=False,
        show_default=False,
        console=console
    ).strip()


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception as e:
            log_debug("stdout.reconfigure", e)

    config.load()
    check_environment()

    while True:
        configured = config.is_configured()
        choice = show_main_menu()

        if choice == "0":
            console.print(f"[{C['muted']}]Bye.[/{C['muted']}]")
            break

        if not configured:
            if choice == "1":
                run_setup()
            continue

        if choice == "8":
            settings_menu()
            continue

        run_downloads(choice)


if __name__ == "__main__":
    main()
