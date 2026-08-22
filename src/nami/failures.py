"""Translate command failures into stable, user-facing categories."""

from __future__ import annotations

import re
from collections.abc import Iterable

from nami.models import FailureKind
from nami.process import CommandResult


def _contains_any(text: str, diagnostics: Iterable[str]) -> bool:
    return any(diagnostic in text for diagnostic in diagnostics)


def classify_failure(result: CommandResult) -> FailureKind | None:
    """Classify a failed command using flags, then ordered diagnostics."""

    if result.cancelled:
        # Cancellation is represented by Outcome.CANCELLED, not FailureKind.
        return None
    if result.timed_out:
        return FailureKind.TIMEOUT
    if result.returncode == 0:
        return None

    text = "\n".join((*result.lines, result.output_tail)).casefold()

    # Require an actual authentication or cookie-loading diagnostic. Merely
    # mentioning that cookies were supplied must never turn a failure into auth.
    if _contains_any(
        text,
        (
            "http error 401",
            "status code 401",
            "login required",
            "authentication required",
            "not logged in",
            "please log in",
            "sign in to confirm",
            "cookies are no longer valid",
            "cookies have expired",
        ),
    ):
        return FailureKind.AUTH

    if _contains_any(
        text,
        (
            "failed to decrypt cookies",
            "failed to load cookies",
            "unable to load cookies",
            "could not copy browser cookie database",
            "could not find browser cookies",
            "could not find chrome cookie",
            "could not find brave cookie",
            "cookie file not found",
            "no cookies found",
            "cookiejar error",
        ),
    ):
        return FailureKind.COOKIE

    if _contains_any(
        text,
        (
            "checkpoint_required",
            "challenge_required",
            "checkpoint required",
            "suspicious login",
            "account checkpoint",
        ),
    ):
        return FailureKind.LOCKED

    if re.search(r"(?:http(?: error)?|status(?: code)?)\s*[:=]?\s*429\b", text) or _contains_any(
        text,
        ("too many requests", "rate limit", "rate-limit", "ratelimit", "throttled"),
    ):
        return FailureKind.RATE_LIMIT

    if _contains_any(
        text,
        (
            "unable to download webpage",
            "unable to connect",
            "connection refused",
            "connection reset",
            "connection aborted",
            "network is unreachable",
            "temporary failure in name resolution",
            "name or service not known",
            "nodename nor servname provided",
            "remote end closed connection",
            "read timed out",
            "connect timeout",
            "connection timeout",
            "ssl certificate verify failed",
        ),
    ):
        return FailureKind.NETWORK

    if _contains_any(
        text,
        (
            "modulenotfounderror",
            "no module named",
            "importerror:",
            "missing dependency",
            "module 'urllib3'",
            'module "urllib3"',
            "urllib3-future",
            "niquests",
            "attributeerror: module",
        ),
    ):
        return FailureKind.DEPENDENCY

    if _contains_any(
        text,
        (
            "no results for",
            "no matching media found",
            "no media found",
            "nothing to download",
            "requested content is not available",
            "this content isn't available",
            "this content is not available",
            "content not found",
            "user not found",
            "profile not found",
            "http error 404",
            "status code 404",
        ),
    ):
        return FailureKind.NOT_FOUND

    if _contains_any(
        text,
        (
            "unsupported url",
            "unsupported site",
            "no suitable extractor",
            "extractor not found",
            "no extractor could handle",
        ),
    ):
        return FailureKind.EXTRACTOR

    return FailureKind.UNKNOWN


_FAILURE_MESSAGES = {
    FailureKind.AUTH: "Authentication was rejected",
    FailureKind.COOKIE: "Cookies could not be loaded",
    FailureKind.RATE_LIMIT: "The platform rate limit was reached",
    FailureKind.NETWORK: "A network error interrupted the download",
    FailureKind.EXTRACTOR: "The downloader could not extract this URL",
    FailureKind.NOT_FOUND: "No matching content was found",
    FailureKind.DEPENDENCY: "A downloader dependency is unavailable",
    FailureKind.TIMEOUT: "The downloader timed out",
    FailureKind.LOCKED: "The account or archive is locked",
    FailureKind.CONFIG: "The download configuration is invalid",
    FailureKind.UNKNOWN: "The downloader failed for an unknown reason",
}


def failure_message(failure: FailureKind) -> str:
    """Return user-facing explanation for a FailureKind."""
    return _FAILURE_MESSAGES.get(failure, "The downloader failed for an unknown reason")


classify_command_result = classify_failure
