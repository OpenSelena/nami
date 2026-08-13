"""Diagnostic tools and health checks for Nami."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from typing import Any

from nami.retry import FailureType, classify_failure


def diagnose_log(log_path: Path | str, tool_name: str) -> str:
    path = Path(log_path)
    if not path.exists():
        return f"No log file found at {log_path}"
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        failure = classify_failure(1, content)

        if failure == FailureType.AUTH:
            return f"[{tool_name}] AUTH failure - session/cookies invalid or not accepted."
        elif failure == FailureType.RATE_LIMIT:
            return f"[{tool_name}] RATE LIMITED - HTTP 429 received. Back off before retrying."
        elif failure == FailureType.NOT_FOUND:
            return f"[{tool_name}] NOT FOUND - Target profile or media does not exist or is private."
        elif failure == FailureType.NETWORK:
            return f"[{tool_name}] NETWORK failure - Check internet connection and DNS settings."
        elif failure == FailureType.DEPENDENCY:
            return f"[{tool_name}] DEPENDENCY CONFLICT - urllib3 namespace conflict detected."
        elif failure == FailureType.EXTRACTOR:
            return f"[{tool_name}] EXTRACTOR ERROR - Tool could not parse content structure."
        else:
            return f"[{tool_name}] Unrecognized failure - see log file for details."
    except Exception as e:
        return f"[{tool_name}] Log diagnostic error: {e}"


def probe_urllib3_identity() -> tuple[bool, str]:
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
            return False, f"probe failed: {result.stderr.strip()[:200]}"
        output = result.stdout.strip()
        if output.count("|") < 2:
            return False, f"unexpected output: {output[:200]}"
        file_path, version, owner = output.split("|", 2)
        markers = ("urllib3_future", "urllib3-future", "niquests")
        path_hijacked = any(m in file_path.lower() for m in markers)
        meta_hijacked = any(m in owner.lower() for m in markers)
        return (path_hijacked or meta_hijacked), (
            f"urllib3 resolves to: {file_path or '(no __file__)'} "
            f"(version: {version}, owner: {owner})"
        )
    except Exception as e:
        return False, f"probe exception: {e}"


def check_environment_health() -> dict[str, Any]:
    missing = []
    if importlib.util.find_spec("gallery_dl") is None:
        missing.append("gallery-dl")
    if importlib.util.find_spec("yt_dlp") is None:
        missing.append("yt-dlp")
    if importlib.util.find_spec("instaloader") is None:
        missing.append("instaloader")

    is_hijacked, detail = probe_urllib3_identity()
    return {
        "missing_dependencies": missing,
        "urllib3_hijacked": is_hijacked,
        "urllib3_detail": detail,
    }
