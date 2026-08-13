"""Unit tests for failure classification and intelligent retry strategy."""

from nami.retry import (
    classify_failure,
    FailureType,
    execute_with_intelligent_retry,
)


def test_classify_auth_failure():
    log = "ERROR: [instagram] login required. Please log in first."
    assert classify_failure(1, log) == FailureType.AUTH


def test_classify_rate_limit_failure():
    log = "HTTP Error 429: Too Many Requests"
    assert classify_failure(1, log) == FailureType.RATE_LIMIT


def test_classify_not_found_failure():
    log = "ERROR: [instagram] User not found or profile is private."
    assert classify_failure(1, log) == FailureType.NOT_FOUND


def test_classify_network_failure():
    log = "urllib.error.URLError: <urlopen error name or service not known>"
    assert classify_failure(1, log) == FailureType.NETWORK


def test_retry_preserves_cookies_on_rate_limit(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    attempts_cookies = []

    def mock_attempt(cookies: list[str], silent: bool):
        attempts_cookies.append(list(cookies))
        return 1, "HTTP Error 429: Too Many Requests", ""

    rc, ftype, output = execute_with_intelligent_retry(
        mock_attempt, ["--cookies", "valid.txt"], None, "test_tool", max_retries=1
    )

    assert ftype == FailureType.RATE_LIMIT
    # Verify cookies were NOT stripped across retries
    for cookie_arg in attempts_cookies:
        assert cookie_arg == ["--cookies", "valid.txt"]

