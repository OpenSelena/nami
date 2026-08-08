#!/usr/bin/env python3
"""
Nami v2.3.7 — multi-platform media downloader (gallery-dl + yt-dlp)

First-run Setup creates:

    <you choose>/Nami/
        downloads/     media
        cookies/       Netscape cookie files
        profiles/      profile URL lists

Paths are saved in ~/.nami/nami_config.json.
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
import urllib.parse
import time
import importlib.util
from pathlib import Path

try:
    from importlib.metadata import version as pkg_version
    __version__ = pkg_version("nami")
except Exception:
    __version__ = "2.3.7"

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.align import Align
    from rich.text import Text
    from rich.box import ROUNDED
    from rich.prompt import Prompt
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn,
        TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
    )
except ImportError:
    print("[FATAL] The 'rich' library is required to run this script.")
    print("Please install it by running: pip install rich")
    sys.exit(1)

CONFIG_DIR = Path.home() / ".nami"
CONFIG_FILE = CONFIG_DIR / "nami_config.json"
PLATFORMS = ("instagram", "tiktok", "facebook", "x")
PROFILE_FILES = tuple(f"{p}_profiles.txt" for p in PLATFORMS)


def clear_screen() -> None:
    """Hard clear — Rich clear alone is unreliable in Windows Terminal."""
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")
    try:
        console.clear()
    except Exception:
        pass


def _detect_theme() -> str:
    """
    Optional override only. Body text no longer depends on this value for
    readability — primary/secondary/muted use the terminal's default
    foreground so they always contrast with whatever background the user set.

    NAMI_THEME=light|dark still tweaks accent/warning/error shades slightly.
    """
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

    # Windows Terminal often keeps classic conhost attributes at "dark"
    # even when the visual theme is light, so we do not trust Win32 here.
    return "dark"


THEME = _detect_theme()

# primary / secondary / muted intentionally use the terminal default
# foreground (no forced white/black). That way labels stay readable on
# both light and dark backgrounds without perfect theme detection.
# Accent and status colors stay branded orange / semantic.
C = {
    # "default" = terminal's own foreground (always contrasts with bg)
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
    """
    Create a Rich Console that respects:
    - NO_COLOR / FORCE_COLOR environment variables
    - Whether stdout is a real TTY
    - Terminal color capability
    """
    # Standard NO_COLOR convention → disable all color
    if os.environ.get("NO_COLOR"):
        return Console(force_terminal=False, no_color=True, color_system=None)

    # FORCE_COLOR=1 is also a common convention
    force = os.environ.get("FORCE_COLOR", "").strip().lower() in ("1", "true", "yes")

    return Console(
        force_terminal=True if force else None,  # None = auto-detect TTY
        color_system="auto",                     # let Rich choose best system
        highlight=False,
    )


console = _make_console()

BASE_DIR: Path | None = None
COOKIES_DIR: Path | None = None
PROFILES_DIR: Path | None = None
BROWSER: str = "brave"
UA = os.environ.get(
    "NAMI_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
MAX_RETRIES = 2
DEBUG_LOG: Path | None = None

PHOTO_FILTER = (
    "extension in ('jpg','jpeg','png','gif','webp','bmp','jfif',"
    "'heic','avif','tiff','svg')"
)
VIDEO_FILTER = (
    "extension in ('mp4','webm','mkv','mov','avi','m4v','flv','wmv',"
    "'3gp','mpeg','mpg','ts','f4v','mts','m2ts')"
)
MEDIA_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".jfif", ".heic",
    ".avif", ".tiff", ".svg", ".mp4", ".webm", ".mkv", ".mov", ".avi",
    ".m4v", ".flv", ".wmv", ".3gp", ".mpeg", ".mpg", ".ts", ".f4v",
    ".mts", ".m2ts",
}


def is_configured() -> bool:
    if BASE_DIR is None or COOKIES_DIR is None or PROFILES_DIR is None:
        return False
    try:
        return BASE_DIR.is_dir() and COOKIES_DIR.is_dir() and PROFILES_DIR.is_dir()
    except OSError:
        return False


def load_config() -> None:
    global BASE_DIR, COOKIES_DIR, PROFILES_DIR, BROWSER, DEBUG_LOG

    BASE_DIR = None
    COOKIES_DIR = None
    PROFILES_DIR = None
    BROWSER = "brave"
    DEBUG_LOG = None

    if not CONFIG_FILE.exists():
        if os.environ.get("NAMI_BASE_DIR") and os.environ.get("NAMI_COOKIES_DIR"):
            try:
                BASE_DIR = Path(os.environ["NAMI_BASE_DIR"]).expanduser().resolve()
                COOKIES_DIR = Path(os.environ["NAMI_COOKIES_DIR"]).expanduser().resolve()
                env_prof = os.environ.get("NAMI_PROFILES_DIR")
                if env_prof:
                    PROFILES_DIR = Path(env_prof).expanduser().resolve()
                else:
                    PROFILES_DIR = BASE_DIR.parent / "profiles"
                BROWSER = os.environ.get("NAMI_BROWSER", "brave").strip() or "brave"
                DEBUG_LOG = BASE_DIR / "nami_debug.log"
            except Exception as e:
                console.print(
                    f"[{C['error']}][ERROR] Invalid NAMI_* path environment variables: {e}"
                    f"[/{C['error']}]"
                )
                BASE_DIR = COOKIES_DIR = PROFILES_DIR = None
        return

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return
    except (json.JSONDecodeError, OSError) as e:
        console.print(
            f"[{C['warning']}][WARN] Could not read {CONFIG_FILE.name}: {e}"
            f"[/{C['warning']}]"
        )
        return

    base = data.get("base_dir") or os.environ.get("NAMI_BASE_DIR")
    cookies = data.get("cookies_dir") or os.environ.get("NAMI_COOKIES_DIR")
    profiles = data.get("profiles_dir") or os.environ.get("NAMI_PROFILES_DIR")
    browser = data.get("browser") or os.environ.get("NAMI_BROWSER") or "brave"

    if base:
        try:
            BASE_DIR = Path(str(base)).expanduser().resolve()
        except Exception:
            BASE_DIR = None
    if cookies:
        try:
            COOKIES_DIR = Path(str(cookies)).expanduser().resolve()
        except Exception:
            COOKIES_DIR = None
    if profiles:
        try:
            PROFILES_DIR = Path(str(profiles)).expanduser().resolve()
        except Exception:
            PROFILES_DIR = None
    elif BASE_DIR is not None:
        # Older configs without profiles_dir → sibling of downloads
        PROFILES_DIR = BASE_DIR.parent / "profiles"

    BROWSER = str(browser).strip() or "brave"
    if BASE_DIR is not None:
        DEBUG_LOG = BASE_DIR / "nami_debug.log"


def save_config() -> bool:
    if BASE_DIR is None or COOKIES_DIR is None or PROFILES_DIR is None:
        console.print(
            f"[{C['error']}][ERROR] Cannot save config: directories not set."
            f"[/{C['error']}]"
        )
        return False
    data = {
        "base_dir": str(BASE_DIR),
        "cookies_dir": str(COOKIES_DIR),
        "profiles_dir": str(PROFILES_DIR),
        "browser": BROWSER,
    }
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        console.print(f"[{C['error']}][ERROR] Failed to save config: {e}[/{C['error']}]")
        return False


def ensure_dirs() -> bool:
    if BASE_DIR is None or COOKIES_DIR is None or PROFILES_DIR is None:
        return False
    try:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        COOKIES_DIR.mkdir(parents=True, exist_ok=True)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        for name in PROFILE_FILES:
            path = PROFILES_DIR / name
            if not path.exists():
                path.write_text("# One profile URL per line\n", encoding="utf-8")
        return True
    except OSError as e:
        console.print(
            f"[{C['error']}][ERROR] Cannot create directories: {e}[/{C['error']}]"
        )
        return False


def log_debug(context, exc) -> None:
    if DEBUG_LOG is None:
        return
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {context}: {repr(exc)}\n")
    except Exception:
        pass


def run_setup() -> bool:
    """Create Nami folders, empty profile lists, save config."""
    global BASE_DIR, COOKIES_DIR, PROFILES_DIR, DEBUG_LOG

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

    try:
        downloads.mkdir(parents=True, exist_ok=True)
        cookies.mkdir(parents=True, exist_ok=True)
        profiles.mkdir(parents=True, exist_ok=True)
        for name in PROFILE_FILES:
            path = profiles / name
            if not path.exists():
                path.write_text("# One profile URL per line\n", encoding="utf-8")
    except OSError as e:
        console.print(f"[{C['error']}]Failed: {e}[/{C['error']}]")
        input("\nPress Enter...")
        return False

    BASE_DIR = downloads
    COOKIES_DIR = cookies
    PROFILES_DIR = profiles
    DEBUG_LOG = BASE_DIR / "nami_debug.log"

    if not save_config():
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


def probe_urllib3_identity():
    probe_script = (
        "import urllib3, sys\n"
        "path = getattr(urllib3, '__file__', '') or ''\n"
        "version = getattr(urllib3, '__version__', 'unknown')\n"
        "owner = 'unknown'\n"
        "try:\n"
        " from importlib.metadata import distribution\n"
        " owner = distribution('urllib3').metadata.get('Name', 'unknown')\n"
        "except Exception:\n"
        " pass\n"
        "print(f'{path}|{version}|{owner}')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe_script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return False, f"probe failed to run: {result.stderr.strip()[:200]}"
        output = result.stdout.strip()
        if output.count("|") < 2:
            return False, f"unexpected probe output: {output[:200]}"
        file_path, version, owner = output.split("|", 2)
        file_path_lower = file_path.lower()
        owner_lower = owner.lower()
        markers = ("urllib3_future", "urllib3-future", "niquests")
        path_hijacked = any(m in file_path_lower for m in markers)
        meta_hijacked = any(m in owner_lower for m in markers)
        return (path_hijacked or meta_hijacked), (
            f"urllib3 resolves to: {file_path or '(no __file__)'} "
            f"(version reported: {version}, distribution owner: {owner})"
        )
    except subprocess.TimeoutExpired:
        return False, "probe timed out"
    except Exception as e:
        log_debug("probe_urllib3_identity", e)
        return False, f"probe raised: {e}"


def check_environment() -> None:
    if os.environ.get("NAMI_SKIP_ENV_CHECK") == "1":
        return

    missing = []
    if importlib.util.find_spec("gallery_dl") is None:
        missing.append("gallery-dl")
    if importlib.util.find_spec("yt_dlp") is None:
        missing.append("yt-dlp")
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

    present_pkgs = []
    for pkg in ("urllib3_future", "niquests"):
        if importlib.util.find_spec(pkg) is not None:
            present_pkgs.append(pkg.replace("_", "-"))

    is_hijacked, detail = probe_urllib3_identity()
    if is_hijacked:
        console.print(Panel.fit(
            f"[{C['error']}]urllib3 namespace IS hijacked in this environment.[/{C['error']}]\n"
            f"[{C['secondary']}]{detail}[/{C['secondary']}]\n"
            f"[{C['secondary']}]gallery-dl and yt-dlp may fail networking. Fix with:[/{C['secondary']}]\n"
            f"[bold]{sys.executable} -m pip uninstall "
            f"{' '.join(present_pkgs) or 'urllib3-future niquests'}[/bold]\n"
            f"[bold]{sys.executable} -m pip install --force-reinstall urllib3[/bold]",
            border_style="red",
            title=f"[{C['error']}]Dependency Conflict Confirmed[/{C['error']}]"
        ))
        time.sleep(2)
    elif present_pkgs:
        log_debug(
            "check_environment",
            f"{', '.join(present_pkgs)} present but not hijacking. {detail}"
        )


def is_brave_running() -> bool:
    """Return True if a Brave process appears to be running."""
    try:
        if sys.platform == "win32":
            res = subprocess.run(
                ["tasklist", "/fi", "imagename eq brave.exe"],
                capture_output=True, text=True, timeout=5
            )
            return "brave.exe" in res.stdout.lower()
        else:
            # macOS / Linux
            res = subprocess.run(
                ["pgrep", "-f", "Brave"],
                capture_output=True, text=True, timeout=5
            )
            return bool(res.stdout.strip())
    except Exception as e:
        log_debug("is_brave_running", e)
        return False


def validate_cookie(file_path) -> bool:
    path = Path(file_path)
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "Netscape HTTP Cookie File" in content:
            return True
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                if len(line.split("\t")) >= 7:
                    return True
                break
    except Exception as e:
        log_debug(f"validate_cookie({file_path})", e)
    return False


def check_archive(directory, archive_file) -> None:
    dir_path = Path(directory)
    archive_path = Path(archive_file)
    if not dir_path.exists():
        if archive_path.exists():
            try:
                archive_path.unlink()
            except Exception as e:
                log_debug(f"check_archive unlink({archive_path})", e)
        return

    try:
        media_count = sum(
            1 for item in dir_path.iterdir()
            if item.is_file() and item.suffix.lower() in MEDIA_EXTS
        )
    except OSError as e:
        log_debug(f"check_archive({directory})", e)
        return

    if media_count == 0:
        if archive_path.exists():
            try:
                archive_path.unlink()
                console.print(f" [{C['muted']}]Empty, archive cleared.[/{C['muted']}]")
            except Exception as e:
                log_debug(f"check_archive unlink({archive_path})", e)
    else:
        if not archive_path.exists():
            console.print(
                f" [{C['muted']}]{media_count} files, archive missing "
                f"(will be created).[/{C['muted']}]"
            )
        else:
            console.print(f" [{C['muted']}]{media_count} files, archive ok.[/{C['muted']}]")


def looks_like_media_output_line(line: str) -> bool:
    candidate = line.strip()
    if candidate.startswith("#"):
        candidate = candidate[1:].strip()
    if not candidate:
        return False
    has_sep = ("/" in candidate or "\\" in candidate)
    ext = os.path.splitext(candidate)[1].lower()
    return has_sep and ext in MEDIA_EXTS


def run_command(cmd, silent_log_path=None, progress_obj=None, active_task_id=None):
    try:
        if silent_log_path:
            log_dir = Path(silent_log_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(silent_log_path, "w", encoding="utf-8", errors="replace") as f:
                res = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
            return res.returncode

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1
        )
        items_processed = 0
        try:
            for line in process.stdout:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                if looks_like_media_output_line(line_stripped):
                    items_processed += 1
                    file_name = os.path.basename(line_stripped.lstrip("#").strip())
                    if line_stripped.startswith("#"):
                        console.print(f" [{C['muted']}]# {file_name}[/{C['muted']}]")
                        if progress_obj is not None and active_task_id is not None:
                            progress_obj.update(
                                active_task_id,
                                completed=items_processed,
                                total=None,
                                status=f"[{C['muted']}]Checking: {file_name[:25]}...[/{C['muted']}]"
                            )
                    else:
                        console.print(f" [{C['accent_b']}]-> {file_name}[/{C['accent_b']}]")
                        if progress_obj is not None and active_task_id is not None:
                            progress_obj.update(
                                active_task_id,
                                completed=items_processed,
                                total=None,
                                status=(
                                    f"[{C['accent_b']}]Downloaded: "
                                    f"{file_name[:25]}...[/{C['accent_b']}]"
                                )
                            )
                else:
                    console.print(f" [{C['muted']}]{line_stripped}[/{C['muted']}]")
            process.wait(timeout=7200)  # 2h safety net against permanent hangs
            return process.returncode
        except subprocess.TimeoutExpired:
            console.print(f" [{C['error']}][ERROR] Download timed out after 2 hours[/{C['error']}]")
            process.kill()
            return 1
        except KeyboardInterrupt:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
            raise
    except KeyboardInterrupt:
        raise
    except Exception as e:
        console.print(f" [{C['error']}][ERROR] Command failed to run: {e}[/{C['error']}]")
        log_debug(f"run_command({cmd})", e)
        return 1


def diagnose_log(log_path, tool_name) -> None:
    path = Path(log_path)
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().lower()
        console.print(Panel.fit(
            f"[{C['error']}]Download Diagnostics ({tool_name})[/{C['error']}]\n",
            border_style="red"
        ))
        if any(kw in content for kw in (
            "401", "login required", "not logged in", "authentication",
            "please log in", "redirect", "redirected"
        )):
            console.print(
                f" [{C['error']}][DIAGNOSIS] AUTH failure - session/cookies "
                f"not accepted.[/{C['error']}]"
            )
        elif any(kw in content for kw in (
            "checkpoint", "challenge_required", "suspicious login"
        )):
            console.print(
                f" [{C['error']}][DIAGNOSIS] account CHECKPOINT/CHALLENGE - "
                f"verify in a real browser first.[/{C['error']}]"
            )
        elif any(kw in content for kw in ("429", "rate", "too many requests")):
            console.print(
                f" [{C['error']}][DIAGNOSIS] RATE LIMITED - back off and "
                f"retry later.[/{C['error']}]"
            )
        elif any(kw in content for kw in (
            "no cookies", "cookiejar", "could not find brave cookie",
            "could not find chrome cookie"
        )):
            console.print(
                f" [{C['error']}][DIAGNOSIS] cookie source could not be read. "
                f"Close the browser fully if using --cookies-from-browser.[/{C['error']}]"
            )
        elif any(kw in content for kw in (
            "unable to download webpage", "connection", "timed out", "timeout"
        )):
            console.print(
                f" [{C['error']}][DIAGNOSIS] NETWORK failure, not auth. "
                f"Check connection.[/{C['error']}]"
            )
        elif any(kw in content for kw in (
            "module 'urllib3'", "niquests", "urllib3-future", "attributeerror: module"
        )):
            console.print(
                f" [{C['error']}][DIAGNOSIS] possible urllib3 namespace conflict "
                f"(urllib3-future/niquests).[/{C['error']}]"
            )
        else:
            console.print(
                f" [{C['error']}][DIAGNOSIS] unrecognized failure - see "
                f"{log_path} for details.[/{C['error']}]"
            )
    except Exception as e:
        console.print(
            f" [{C['error']}][ERROR] Failed to read log for diagnosis: {e}[/{C['error']}]"
        )
        log_debug(f"diagnose_log({log_path})", e)


def parse_url(url, platform):
    if not url.startswith("http"):
        url = "https://" + url
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        # Strip common mobile / subdomain prefixes
        for prefix in ("www.", "m.", "mobile.", "vm.", "business."):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
                break

        valid_domains = {
            "instagram": ["instagram.com"],
            "tiktok": ["tiktok.com"],
            "facebook": ["facebook.com"],
            "x": ["x.com", "twitter.com"],
        }
        if domain not in valid_domains.get(platform, []):
            return "INVALID_URL"

        path = parsed.path.strip("/")
        path_parts = [p for p in path.split("/") if p]
        if not path_parts:
            return None

        # Facebook numeric ID format: /profile.php?id=123456789
        if path_parts[0].lower() == "profile.php":
            query = urllib.parse.parse_qs(parsed.query)
            ids = query.get("id")
            if ids and ids[0].isdigit():
                return ids[0]
            return None

        username = path_parts[0].replace("@", "")
        # Reject common non-profile path segments across platforms
        if username.lower() in (
            "p", "reel", "tv", "highlights", "stories",
            "groups", "events", "hashtag", "i", "explore", "reels"
        ):
            return None
        username = username.split("?")[0].split("#")[0]
        return username if username else None
    except Exception as e:
        log_debug(f"parse_url({url}, {platform})", e)
        return "INVALID_URL"


def get_cookies_arg(platform):
    if COOKIES_DIR is None:
        # Still allow browser cookies for TikTok even without a cookies dir
        if platform == "tiktok":
            if is_brave_running():
                console.print(
                    f" [{C['warning']}][WARN] Brave is currently running - TikTok "
                    f"cookie read via --cookies-from-browser may get a locked/"
                    f"stale DB. Close Brave fully if TikTok keeps failing."
                    f"[/{C['warning']}]"
                )
            return ["--cookies-from-browser", BROWSER]
        return []

    # Prefer explicit Netscape cookie file for every platform (including TikTok)
    cookie_file = COOKIES_DIR / f"{platform}.com_cookies.txt"
    if cookie_file.exists():
        if validate_cookie(cookie_file):
            return ["--cookies", str(cookie_file)]
        console.print(
            f" [{C['warning']}][WARN] Cookie file {cookie_file.name} failed "
            f"validation, continuing without cookies.[/{C['warning']}]"
        )

    # Fallback for TikTok: browser cookies
    if platform == "tiktok":
        if is_brave_running():
            console.print(
                f" [{C['warning']}][WARN] Brave is currently running - TikTok "
                f"cookie read via --cookies-from-browser may get a locked/"
                f"stale DB. Close Brave fully if TikTok keeps failing."
                f"[/{C['warning']}]"
            )
        return ["--cookies-from-browser", BROWSER]

    return []


def download_gd(directory, filter_str, cookies_arg, url, sleep_time="5",
                silent=False, progress_obj=None, active_task_id=None):
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "gallery_dl",
        "-D", str(dir_path),
        "-o", f"user-agent={UA}",
        "--download-archive", str(dir_path / "archive.txt"),
        "--sleep-request", sleep_time,
    ]
    if filter_str:
        cmd.extend(["--filter", filter_str])
    cmd.extend(cookies_arg)
    cmd.append(url)
    log_path = str(dir_path / "lastrun.log") if silent else None
    return run_command(
        cmd, silent_log_path=log_path,
        progress_obj=progress_obj, active_task_id=active_task_id
    )


def download_yt(directory, cookies_arg, url, silent=False,
                progress_obj=None, active_task_id=None):
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-o", str(dir_path / "%(title)s.%(ext)s"),
        "--no-playlist",
        "--user-agent", UA,
        "--download-archive", str(dir_path / "archive.txt"),
    ]
    cmd.extend(cookies_arg)
    cmd.append(url)
    log_path = str(dir_path / "lastrun.log") if silent else None
    return run_command(
        cmd, silent_log_path=log_path,
        progress_obj=progress_obj, active_task_id=active_task_id
    )


def retry_with_cookie_fallback(attempt_fn, cookies_arg, log_file, tool_name,
                               cookie_reject_context=""):
    current_cookies = cookies_arg
    for attempt in range(MAX_RETRIES + 1):
        rc = attempt_fn(current_cookies, False)
        if rc == 0:
            return 0
        if rc != 0 and current_cookies:
            suffix = f" {cookie_reject_context}" if cookie_reject_context else ""
            console.print(
                f" [{C['warning']}]Cookies rejected/blocked{suffix}. "
                f"Retrying anonymous fallback run...[/{C['warning']}]"
            )
            current_cookies = []
            time.sleep(3)  # short backoff after credential rejection
            continue
        if attempt < MAX_RETRIES:
            wait_time = (attempt + 1) * 10
            console.print(
                f" [{C['warning']}]{tool_name} failed (code {rc}), "
                f"retry {attempt + 1}/{MAX_RETRIES} in {wait_time}s..."
                f"[/{C['warning']}]"
            )
            time.sleep(wait_time)
        else:
            attempt_fn(current_cookies, True)
            diagnose_log(log_file, tool_name)
            return rc
    return 1


def retry_gd(directory, filter_str, cookies_arg, url,
             progress_obj=None, active_task_id=None, platform_name=""):
    log_file = Path(directory) / "lastrun.log"

    def attempt(cookies, silent):
        sleep_time = "1" if silent else "5"
        return download_gd(
            directory, filter_str, cookies, url,
            sleep_time=sleep_time, silent=silent,
            progress_obj=progress_obj, active_task_id=active_task_id
        )

    context = f"by {platform_name.capitalize()}" if platform_name else ""
    return retry_with_cookie_fallback(
        attempt, cookies_arg, log_file, "gallery-dl",
        cookie_reject_context=context
    )


def retry_yt(directory, cookies_arg, url,
             progress_obj=None, active_task_id=None, platform_name=""):
    log_file = Path(directory) / "lastrun.log"

    def attempt(cookies, silent):
        return download_yt(
            directory, cookies, url, silent=silent,
            progress_obj=progress_obj, active_task_id=active_task_id
        )

    context = f"by {platform_name.capitalize()}" if platform_name else ""
    return retry_with_cookie_fallback(
        attempt, cookies_arg, log_file, "yt-dlp",
        cookie_reject_context=context
    )


def process_photos(target_dir, cookies_arg, url, platform="",
                   progress_obj=None, active_task_id=None):
    check_archive(target_dir / "Photos", target_dir / "Photos/archive.txt")
    console.print(f" [{C['primary']}]Checking Photos...[/{C['primary']}]")
    rc = retry_gd(
        target_dir / "Photos", PHOTO_FILTER, cookies_arg, url,
        progress_obj=progress_obj, active_task_id=active_task_id, platform_name=platform
    )
    if rc != 0:
        console.print(
            f" [{C['error']}][ERROR] gallery-dl exited with code {rc} "
            f"after retries[/{C['error']}]"
        )
    return rc


def process_videos(target_dir, cookies_arg, url, platform="",
                   progress_obj=None, active_task_id=None):
    check_archive(target_dir / "Videos", target_dir / "Videos/archive.txt")
    console.print(f" [{C['primary']}]Checking Videos...[/{C['primary']}]")
    rc = retry_gd(
        target_dir / "Videos", VIDEO_FILTER, cookies_arg, url,
        progress_obj=progress_obj, active_task_id=active_task_id, platform_name=platform
    )
    if rc != 0:
        console.print(
            f" [{C['warning']}]gallery-dl failed after retries, trying yt-dlp..."
            f"[/{C['warning']}]"
        )
        yt_rc = retry_yt(
            target_dir / "Videos", cookies_arg, url,
            progress_obj=progress_obj, active_task_id=active_task_id, platform_name=platform
        )
        if yt_rc != 0:
            console.print(
                f" [{C['error']}][ERROR] yt-dlp also failed with code {yt_rc} "
                f"after retries[/{C['error']}]"
            )
        return yt_rc
    return rc


def process_stories(target_dir, cookies_arg, platform, username,
                    progress_obj=None, active_task_id=None):
    if platform != "instagram":
        console.print(
            f" [{C['muted']}][Stories] [SKIP] Not supported for {platform}"
            f"[/{C['muted']}]"
        )
        return 0
    check_archive(target_dir / "Stories", target_dir / "Stories/archive.txt")
    console.print(f" [{C['primary']}]Checking Stories...[/{C['primary']}]")
    rc = retry_gd(
        target_dir / "Stories", None, cookies_arg,
        f"https://www.instagram.com/stories/{username}/",
        progress_obj=progress_obj, active_task_id=active_task_id, platform_name=platform
    )
    if rc != 0:
        console.print(
            f" [{C['error']}][ERROR] gallery-dl exited with code {rc} "
            f"after retries[/{C['error']}]"
        )
    return rc


def process_highlights(target_dir, cookies_arg, platform, username,
                       progress_obj=None, active_task_id=None):
    if platform != "instagram":
        console.print(
            f" [{C['muted']}][Highlights] [SKIP] Not supported for {platform}"
            f"[/{C['muted']}]"
        )
        return 0
    check_archive(target_dir / "Highlights", target_dir / "Highlights/archive.txt")
    console.print(f" [{C['primary']}]Checking Highlights...[/{C['primary']}]")
    rc = retry_gd(
        target_dir / "Highlights", None, cookies_arg,
        f"https://www.instagram.com/{username}/highlights/",
        progress_obj=progress_obj, active_task_id=active_task_id, platform_name=platform
    )
    if rc != 0:
        console.print(
            f" [{C['error']}][ERROR] gallery-dl exited with code {rc} "
            f"after retries[/{C['error']}]"
        )
    return rc


def download_profile(username, target_dir, platform, original_url, choice,
                     progress_obj, active_task_id):
    cookies_arg = get_cookies_arg(platform)
    clean_url = original_url.rstrip("/")
    if not clean_url.startswith("http"):
        clean_url = "https://" + clean_url

    results = []
    # 1 Photos, 2 Videos, 3 Stories, 4 Highlights,
    # 5 Photos+Videos, 6 Stories+Highlights, 7 All
    if choice == "1":
        results.append(process_photos(
            target_dir, cookies_arg, clean_url, platform, progress_obj, active_task_id
        ))
    elif choice == "2":
        results.append(process_videos(
            target_dir, cookies_arg, clean_url, platform, progress_obj, active_task_id
        ))
    elif choice == "3":
        results.append(process_stories(
            target_dir, cookies_arg, platform, username, progress_obj, active_task_id
        ))
    elif choice == "4":
        results.append(process_highlights(
            target_dir, cookies_arg, platform, username, progress_obj, active_task_id
        ))
    elif choice == "5":
        results.append(process_photos(
            target_dir, cookies_arg, clean_url, platform, progress_obj, active_task_id
        ))
        results.append(process_videos(
            target_dir, cookies_arg, clean_url, platform, progress_obj, active_task_id
        ))
    elif choice == "6":
        results.append(process_stories(
            target_dir, cookies_arg, platform, username, progress_obj, active_task_id
        ))
        results.append(process_highlights(
            target_dir, cookies_arg, platform, username, progress_obj, active_task_id
        ))
    elif choice == "7":
        results.append(process_photos(
            target_dir, cookies_arg, clean_url, platform, progress_obj, active_task_id
        ))
        results.append(process_videos(
            target_dir, cookies_arg, clean_url, platform, progress_obj, active_task_id
        ))
        results.append(process_stories(
            target_dir, cookies_arg, platform, username, progress_obj, active_task_id
        ))
        results.append(process_highlights(
            target_dir, cookies_arg, platform, username, progress_obj, active_task_id
        ))
    return all(r == 0 for r in results)


def _prompt_path(label: str, current: Path) -> Path | None:
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
    except Exception as e:
        console.print(f"[{C['error']}]Invalid path: {e}[/{C['error']}]")
        return None
    try:
        new_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        console.print(
            f"[{C['error']}]Cannot create or access that directory: {e}[/{C['error']}]"
        )
        return None
    return new_path


def settings_menu() -> None:
    global BASE_DIR, COOKIES_DIR, BROWSER, DEBUG_LOG

    if not is_configured():
        console.print(f"[{C['warning']}]Run Setup first.[/{C['warning']}]")
        input("\nPress Enter...")
        return

    while True:
        clear_screen()
        body = Text()
        body.append("  1  ", style=C["accent_b"])
        body.append("Save directory\n", style=C["secondary"])
        body.append(f"     {BASE_DIR}\n\n", style=C["muted"])
        body.append("  2  ", style=C["accent_b"])
        body.append("Cookies directory\n", style=C["secondary"])
        body.append(f"     {COOKIES_DIR}\n\n", style=C["muted"])
        body.append("  3  ", style=C["accent_b"])
        body.append("Browser\n", style=C["secondary"])
        body.append(f"     {BROWSER}\n\n", style=C["muted"])
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
            new_path = _prompt_path("Save directory", BASE_DIR)
            if new_path is not None and new_path != BASE_DIR:
                BASE_DIR = new_path
                DEBUG_LOG = BASE_DIR / "nami_debug.log"
                if save_config():
                    console.print(f"[{C['success']}]Saved.[/{C['success']}]")
                    ensure_dirs()

        elif choice == "2":
            new_path = _prompt_path("Cookies directory", COOKIES_DIR)
            if new_path is not None and new_path != COOKIES_DIR:
                COOKIES_DIR = new_path
                if save_config():
                    console.print(f"[{C['success']}]Saved.[/{C['success']}]")
                    ensure_dirs()

        elif choice == "3":
            console.print(f"[{C['muted']}]brave / chrome / edge / firefox[/{C['muted']}]")
            raw = Prompt.ask(
                f"[{C['accent_b']}]>[/{C['accent_b']}]",
                default=BROWSER,
                console=console
            ).strip().lower()
            if raw and raw != BROWSER:
                BROWSER = raw
                if save_config():
                    console.print(f"[{C['success']}]Saved.[/{C['success']}]")

        elif choice == "4":
            run_setup()

        elif choice == "5":
            return


def run_downloads(choice: str) -> None:
    if not is_configured():
        console.print(f"[{C['warning']}]Run Setup first.[/{C['warning']}]")
        input("\nPress Enter...")
        return

    if not ensure_dirs():
        input("\nPress Enter to continue...")
        return

    original_cwd = Path.cwd()
    try:
        os.chdir(BASE_DIR)
    except OSError as e:
        console.print(
            f"[{C['error']}][ERROR] Cannot change to save directory {BASE_DIR}: {e}"
            f"[/{C['error']}]"
        )
        input("\nPress Enter to continue...")
        return

    platforms = list(PLATFORMS)
    total_profiles = 0
    profiles_to_process = []

    for plat in platforms:
        profile_file = PROFILES_DIR / f"{plat}_profiles.txt"
        if not profile_file.exists():
            continue
        try:
            with open(profile_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_stripped = line.strip()
                    if (not line_stripped
                            or line_stripped.startswith("#")
                            or line_stripped.startswith(";")):
                        continue
                    username = parse_url(line_stripped, plat)
                    if username and username != "INVALID_URL":
                        total_profiles += 1
                        profiles_to_process.append((plat, username, line_stripped))
                    elif username == "INVALID_URL":
                        console.print(
                            f"[{C['warning']}]-> [SKIP] Invalid or mismatched platform "
                            f"URL: {line_stripped}[/{C['warning']}]"
                        )
                    else:
                        console.print(
                            f"[{C['warning']}]-> [SKIP] Could not parse username from: "
                            f"{line_stripped}[/{C['warning']}]"
                        )
        except OSError as e:
            console.print(
                f"[{C['error']}][ERROR] Cannot read {profile_file.name}: {e}"
                f"[/{C['error']}]"
            )

    if total_profiles == 0:
        console.print(
            f"[{C['warning']}]No valid profiles found under:[/{C['warning']}]"
        )
        console.print(f"  [{C['muted']}]{PROFILES_DIR}[/{C['muted']}]")
        console.print(
            f"[{C['muted']}]Add profile URLs to the .txt files in that folder."
            f"[/{C['muted']}]"
        )
        input("\nPress Enter to continue...")
        return

    progress = Progress(
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

    overall_task = progress.add_task(
        f"[{C['primary']}]Overall Progress[/{C['primary']}]",
        total=total_profiles, status=""
    )
    active_task = progress.add_task(
        f"[{C['primary']}]Active Download[/{C['primary']}]",
        total=None, status="Waiting...", visible=False
    )

    header_printed: set[str] = set()
    failed_profiles: list[str] = []

    try:
        with progress:
            for plat, username, original_line in profiles_to_process:
                if plat not in header_printed:
                    header = "X/TWITTER" if plat == "x" else plat.upper()
                    progress.console.print(
                        f"\n[{C['accent_b']}]# {header}[/{C['accent_b']}]"
                    )
                    header_printed.add(plat)

                progress.console.print(
                    f" [{C['primary']}]-> {username}[/{C['primary']}]"
                )
                progress.update(
                    active_task,
                    description=(
                        f"[{C['primary']}]{plat.upper()}: {username}[/{C['primary']}]"
                    ),
                    completed=0,
                    total=None,
                    status="Initializing...",
                    visible=True
                )

                try:
                    success = download_profile(
                        username, BASE_DIR / plat / username, plat,
                        original_line, choice, progress, active_task
                    )
                    if not success:
                        failed_profiles.append(f"{plat.upper()}: {username}")
                except Exception as e:
                    log_debug(f"profile {plat}/{username}", e)
                    failed_profiles.append(f"{plat.upper()}: {username} (crashed)")
                    progress.console.print(
                        f" [{C['error']}][ERROR] Profile crashed: {e}[/{C['error']}]"
                    )

                progress.advance(overall_task, 1)
                progress.update(active_task, visible=False)

            progress.update(
                overall_task,
                status=f"[{C['accent_b']}]Complete![/{C['accent_b']}]"
            )
    except KeyboardInterrupt:
        console.print(f"\n[{C['error']}][INFO] Cancelled by user.[/{C['error']}]")
        return

    console.print()
    if failed_profiles:
        console.print(Panel(
            Align.center(
                f"[{C['warning']}]Downloads completed with some errors:\n"
                + ", ".join(failed_profiles)
                + f"[/{C['warning']}]"
            ),
            border_style="yellow",
            title=f"[{C['warning']}]Warnings[/{C['warning']}]"
        ))
    else:
        console.print(Panel(
            Align.center(
                f"[{C['success']}]All downloads finished successfully![/{C['success']}]"
            ),
            border_style=C["panel_border"]
        ))

    # Restore original working directory (H-4)
    try:
        os.chdir(original_cwd)
    except Exception:
        pass

    input("\nPress Enter to continue...")


def show_main_menu() -> str:
    clear_screen()
    configured = is_configured()
    menu_text = Text()

    if not configured:
        # First launch only — Setup lives here until config exists
        options = [
            ("1", "Setup"),
            ("0", "Exit"),
        ]
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

    if configured and BASE_DIR is not None:
        menu_text.append(f"\n Save: {BASE_DIR}", style=C["muted"])

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

    load_config()
    check_environment()

    while True:
        configured = is_configured()
        choice = show_main_menu()

        if choice == "0":
            console.print(f"[{C['muted']}]Bye.[/{C['muted']}]")
            break

        # First launch: only Setup is available
        if not configured:
            if choice == "1":
                run_setup()
            continue

        if choice == "8":
            settings_menu()
            continue

        console.print(f"[{C['accent_b']}]Mode: {choice}[/{C['accent_b']}]")
        console.print()
        run_downloads(choice)


if __name__ == "__main__":
    main()
