"""UI rendering and Rich console setup for Nami."""

from __future__ import annotations

import os
import sys

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.align import Align
    from rich.text import Text
    from rich.box import ROUNDED
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn,
        TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
    )
except ImportError:
    print("[FATAL] The 'rich' library is required to run Nami.")
    print("Please install it: pip install rich")
    sys.exit(1)


def _detect_theme() -> str:
    explicit = os.environ.get("NAMI_THEME", "auto").strip().lower()
    if explicit in ("light", "dark"):
        return explicit

    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        try:
            parts = colorfgbg.split(";")
            if len(parts) >= 2:
                bg = int(parts[-1])
                if bg in (7, 15):
                    return "light"
                if 0 <= bg <= 8:
                    return "dark"
        except ValueError:
            pass

    return "dark"


THEME = _detect_theme()

C = {
    "primary": "bold default",
    "secondary": "default",
    "muted": "dim",
    "accent": "#C45C2A" if THEME == "light" else "#D97757",
    "accent_b": "bold #C45C2A" if THEME == "light" else "bold #D97757",
    "success": "bold #1a7a3a" if THEME == "light" else "#D97757",
    "warning": "bold #8a5a00" if THEME == "light" else "bold #E6B800",
    "error": "bold #b00020" if THEME == "light" else "bold #FF6B6B",
    "panel_border": "#C45C2A" if THEME == "light" else "#D97757",
    "bar_complete": "#C45C2A" if THEME == "light" else "#D97757",
}


def _make_console() -> Console:
    if os.environ.get("NO_COLOR"):
        return Console(force_terminal=False, no_color=True, color_system=None)

    force = os.environ.get("FORCE_COLOR", "").strip().lower() in ("1", "true", "yes")

    return Console(
        force_terminal=True if force else None,
        color_system="auto",
        highlight=False,
    )


console = _make_console()


def clear_screen() -> None:
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")
    try:
        console.clear()
    except Exception:
        pass


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(style=C["accent_b"]),
        TextColumn(f"[{C['primary']}]{{task.description}}[/{C['primary']}]"),
        TextColumn("|"),
        TextColumn("{task.fields[status]}", justify="left"),
        BarColumn(
            bar_width=20,
            complete_style=C["bar_complete"],
            finished_style=C["bar_complete"]
        ),
        TaskProgressColumn(
            text_format=f"[{C['accent_b']}]{{task.percentage:>3.0f}}%[/{C['accent_b']}]"
        ),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console
    )


def print_summary_table(results_summary: list[dict[str, str]]) -> None:
    """Print structured results table per platform target (implementing recommendation 15 & 16)."""
    if not results_summary:
        return

    table = Table(title="Download Summary", box=ROUNDED, border_style=C["panel_border"])
    table.add_column("Platform", style=C["accent_b"])
    table.add_column("Target / Username", style=C["secondary"])
    table.add_column("Photos", justify="center")
    table.add_column("Videos", justify="center")
    table.add_column("Stories", justify="center")
    table.add_column("Highlights", justify="center")

    for row in results_summary:
        table.add_row(
            row.get("platform", "").upper(),
            row.get("username", ""),
            row.get("photos", "-"),
            row.get("videos", "-"),
            row.get("stories", "-"),
            row.get("highlights", "-"),
        )

    console.print()
    console.print(table)
