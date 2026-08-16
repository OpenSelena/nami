"""Translate command failures into stable, user-facing categories."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import cast

from nami.models import FailureKind
from nami.process import CommandResult


def _failure_kind(*names: str) -> FailureKind:
    for name in names:
        member = getattr(FailureKind, name, None)
        if member is not None:
            return cast(FailureKind, member)
    raise AttributeError(f"FailureKind is missing expected member {names[0]}")


def _contains_any(text: str, diagnostics: Iterable[str]) -> bool:
    return any(diagnostic in text for diagnostic in diagnostics)


def classify_failure(result: CommandResult) -> FailureKind | None:
    """Classify a failed command using flags, then ordered diagnostics."""

    if result.cancelled:
        # Cancellation is represented by Outcome.CANCELLED, not FailureKind.
        return None
    if result.timed_out:
        return _failure_kind("TIMEOUT", "TIMED_OUT")
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
        return _failure_kind("AUTH", "AUTHENTICATION")

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
        return _failure_kind("COOKIE", "AUTH")

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
        return _failure_kind("LOCKED", "CHECKPOINT", "CHALLENGE")

    if re.search(r"(?:http(?: error)?|status(?: code)?)\s*[:=]?\s*429\b", text) or _contains_any(
        text,
        ("too many requests", "rate limit", "rate-limit", "ratelimit", "throttled"),
    ):
        return _failure_kind("RATE_LIMIT", "RATE_LIMITED")

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
        return _failure_kind("NETWORK")

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
        return _failure_kind("DEPENDENCY", "ENVIRONMENT")

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
        return _failure_kind("NOT_FOUND", "NO_RESULTS")

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
        return _failure_kind("EXTRACTOR", "UNSUPPORTED")

    return _failure_kind("UNKNOWN")


classify_command_result = classify_failure
