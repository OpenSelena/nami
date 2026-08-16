from __future__ import annotations

from nami.failures import classify_failure
from nami.models import FailureKind
from nami.process import CommandResult


def result(
    *lines: str,
    returncode: int = 1,
    timed_out: bool = False,
    cancelled: bool = False,
) -> CommandResult:
    return CommandResult(
        returncode=returncode,
        output_tail="\n".join(lines),
        lines=lines,
        timed_out=timed_out,
        cancelled=cancelled,
        duration_seconds=0.1,
    )


def test_success_is_not_a_failure() -> None:
    assert classify_failure(result("login required", returncode=0)) is None


def test_flags_take_precedence_over_diagnostics() -> None:
    assert classify_failure(result("HTTP Error 429", timed_out=True)) is FailureKind.TIMEOUT
    assert classify_failure(result("login required", cancelled=True)) is None


def test_auth_and_cookie_failures_are_distinct_and_explicit() -> None:
    assert classify_failure(result("ERROR: login required")) is FailureKind.AUTH
    assert classify_failure(result("failed to decrypt cookies")) is FailureKind.COOKIE
    assert classify_failure(result("Using cookies from /tmp/cookies.txt; extractor crashed")) is FailureKind.UNKNOWN


def test_diagnostic_precedence_is_stable() -> None:
    assert classify_failure(result("checkpoint_required; HTTP Error 429")) is FailureKind.LOCKED
    assert classify_failure(result("HTTP Error 429; connection reset")) is FailureKind.RATE_LIMIT
    assert classify_failure(result("connection reset in module 'urllib3'")) is FailureKind.NETWORK
    assert classify_failure(result("no results for URL; unsupported URL")) is FailureKind.NOT_FOUND


def test_remaining_diagnostic_categories() -> None:
    assert classify_failure(result("No module named 'yt_dlp'")) is FailureKind.DEPENDENCY
    assert classify_failure(result("user not found")) is FailureKind.NOT_FOUND
    assert classify_failure(result("Unsupported URL: example.test")) is FailureKind.EXTRACTOR
    assert classify_failure(result("downloader exited with status 3")) is FailureKind.UNKNOWN
