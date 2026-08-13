"""Failure classification and intelligent retry strategy for Nami."""

from __future__ import annotations

import time
import random
from enum import Enum
from pathlib import Path
from typing import Callable, Any


class FailureType(Enum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    EXTRACTOR = "extractor"
    NOT_FOUND = "not_found"
    DEPENDENCY = "dependency"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


def classify_failure(exit_code: int, log_content: str) -> FailureType:
    """Classify subprocess failure into structured FailureType based on exit code and log content."""
    if exit_code == 0:
        return FailureType.UNKNOWN
    if exit_code == 124:
        return FailureType.TIMEOUT

    content = log_content.lower()

    if any(kw in content for kw in (
        "401", "login required", "not logged in", "authentication",
        "please log in", "redirected to login", "checkpoint", "challenge_required",
        "suspicious login"
    )):
        return FailureType.AUTH

    if any(kw in content for kw in (
        "429", "rate limit", "too many requests", "http error 429"
    )):
        return FailureType.RATE_LIMIT

    if any(kw in content for kw in (
        "404", "user not found", "account does not exist", "private profile",
        "this account is private", "content unavailable"
    )):
        return FailureType.NOT_FOUND

    if any(kw in content for kw in (
        "unable to download webpage", "connection reset", "timed out", "timeout",
        "name or service not known", "temporary failure in name resolution", "socket"
    )):
        return FailureType.NETWORK

    if any(kw in content for kw in (
        "module 'urllib3'", "niquests", "urllib3-future", "attributeerror: module"
    )):
        return FailureType.DEPENDENCY

    if any(kw in content for kw in (
        "extractorerror", "unsupported url", "no suitable extractor", "unsupported site"
    )):
        return FailureType.EXTRACTOR

    return FailureType.UNKNOWN


def execute_with_intelligent_retry(
    attempt_fn: Callable[[list[str], bool], tuple[int, str, str]],
    cookies_args: list[str],
    log_file: Path | None,
    tool_name: str,
    max_retries: int = 2,
) -> tuple[int, FailureType, str]:
    """
    Execute download attempt with intelligent retry strategy based on classified FailureType.
    Does NOT strip cookies on Rate Limits (429) or Network errors.
    Returns (exit_code, failure_type, stdout_output).
    """
    current_cookies = list(cookies_args)
    last_rc = 1
    last_failure = FailureType.UNKNOWN
    last_output = ""

    for attempt in range(max_retries + 1):
        silent = False
        rc, stdout, stderr = attempt_fn(current_cookies, silent)
        output = stdout + "\n" + stderr

        # Read log file if provided and output is small
        log_content = output
        if log_file and Path(log_file).exists():
            try:
                log_content += "\n" + Path(log_file).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        if rc == 0:
            return 0, FailureType.UNKNOWN, output

        last_rc = rc
        last_output = output
        failure_type = classify_failure(rc, log_content)
        last_failure = failure_type

        # Early exit for non-retryable failures
        if failure_type in (FailureType.NOT_FOUND, FailureType.EXTRACTOR, FailureType.DEPENDENCY):
            return rc, failure_type, output

        # Handle Auth failure: fall back anonymously ONLY if cookies were supplied and rejected
        if failure_type == FailureType.AUTH and current_cookies:
            current_cookies = []
            time.sleep(2)
            continue

        # Handle Rate Limit (429): exponential backoff with jitter, KEEP cookies
        if failure_type == FailureType.RATE_LIMIT:
            wait_time = (2 ** (attempt + 1)) * 5 + random.uniform(1.0, 3.0)
            time.sleep(wait_time)
            continue

        # Handle Network errors: backoff, KEEP cookies
        if failure_type == FailureType.NETWORK:
            wait_time = (attempt + 1) * 8
            time.sleep(wait_time)
            continue

        # Unknown or generic timeout: standard backoff
        if attempt < max_retries:
            time.sleep((attempt + 1) * 5)

    return last_rc, last_failure, last_output
