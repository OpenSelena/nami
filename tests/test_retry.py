import pytest

from nami.models import FailureKind
from nami.retry import RetryPolicy


def test_transient_retries_are_bounded_exponential_and_deterministic() -> None:
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=2,
        max_delay_seconds=5,
        jitter=lambda: 1,
        jitter_ratio=0.5,
    )

    first = policy.decide(FailureKind.NETWORK, attempt=1)
    second = policy.decide(FailureKind.TIMEOUT, attempt=2)
    final = policy.decide(FailureKind.NETWORK, attempt=3)

    assert first.retry_same_engine and first.delay_seconds == 3
    assert second.retry_same_engine and second.delay_seconds == 5
    assert not final.retry
    assert final.delay_seconds == 0


@pytest.mark.parametrize(
    "failure",
    [
        FailureKind.RATE_LIMIT,
        FailureKind.NOT_FOUND,
        FailureKind.DEPENDENCY,
        FailureKind.LOCKED,
        FailureKind.CONFIG,
        FailureKind.UNKNOWN,
    ],
)
def test_terminal_failures_stop_without_fallback(failure: FailureKind) -> None:
    decision = RetryPolicy().decide(failure, alternate_available=True)

    assert not decision.retry
    assert not decision.use_alternate_engine
    assert decision.delay_seconds == 0


def test_extractor_uses_one_available_alternate_without_repeating() -> None:
    policy = RetryPolicy()

    alternate = policy.decide(FailureKind.EXTRACTOR, alternate_available=True)
    exhausted = policy.decide(FailureKind.EXTRACTOR, alternate_available=False)

    assert alternate.retry and alternate.use_alternate_engine
    assert not alternate.retry_same_engine
    assert not exhausted.retry


@pytest.mark.parametrize("failure", [FailureKind.AUTH, FailureKind.COOKIE])
def test_auth_failure_allows_exactly_one_anonymous_retry_only_when_supplied(
    failure: FailureKind,
) -> None:
    policy = RetryPolicy()

    first = policy.decide(failure, auth_supplied=True)
    repeated = policy.decide(
        failure,
        auth_supplied=True,
        anonymous_retry_used=True,
        alternate_available=True,
    )
    already_anonymous = policy.decide(failure, auth_supplied=False)

    assert first.retry and first.use_anonymous
    assert not repeated.retry
    assert not repeated.use_alternate_engine
    assert not already_anonymous.retry


def test_jitter_is_clamped_and_max_retries_alias_counts_retries() -> None:
    policy = RetryPolicy(
        max_retries=1,
        base_delay_seconds=4,
        max_delay_seconds=10,
        jitter=lambda: -100,
    )

    assert policy.decide(FailureKind.NETWORK, attempt=1).delay_seconds == 4
    assert not policy.decide(FailureKind.NETWORK, attempt=2).retry
