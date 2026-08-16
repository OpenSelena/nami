"""Pure retry decisions for download orchestration."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from nami.models import FailureKind

_STOP_IMMEDIATELY = frozenset(
    {
        FailureKind.RATE_LIMIT,
        FailureKind.NOT_FOUND,
        FailureKind.DEPENDENCY,
        FailureKind.LOCKED,
        FailureKind.CONFIG,
        FailureKind.UNKNOWN,
    }
)
_TRANSIENT = frozenset({FailureKind.NETWORK, FailureKind.TIMEOUT})
_AUTH_FAILURES = frozenset({FailureKind.AUTH, FailureKind.COOKIE})


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Describe what the caller should do after one failed attempt."""

    retry: bool
    delay_seconds: float = 0.0
    retry_same_engine: bool = False
    use_alternate_engine: bool = False
    use_anonymous: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if self.delay_seconds < 0:
            raise ValueError("retry delay must not be negative")
        actions = sum((self.retry_same_engine, self.use_alternate_engine, self.use_anonymous))
        if self.retry and actions != 1:
            raise ValueError("a retry decision must select exactly one retry action")
        if not self.retry and (actions or self.delay_seconds):
            raise ValueError("a stop decision cannot include a retry action or delay")


class RetryPolicy:
    """Apply conservative, bounded retry rules without sleeping or downloading."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        max_retries: int | None = None,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        jitter: Callable[[], float] | None = None,
        jitter_ratio: float = 0.25,
    ) -> None:
        if max_retries is not None:
            if max_retries < 0:
                raise ValueError("max_retries must not be negative")
            max_attempts = max_retries + 1
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if base_delay_seconds < 0 or max_delay_seconds < 0:
            raise ValueError("retry delays must not be negative")
        if jitter_ratio < 0:
            raise ValueError("jitter_ratio must not be negative")
        self.max_attempts: int = max_attempts
        self.base_delay_seconds: float = base_delay_seconds
        self.max_delay_seconds: float = max_delay_seconds
        self._jitter: Callable[[], float] = jitter or random.random
        self.jitter_ratio: float = jitter_ratio

    def decide(
        self,
        failure_kind: FailureKind,
        attempt: int = 1,
        auth_supplied: bool = False,
        anonymous_retry_used: bool = False,
        alternate_available: bool = False,
    ) -> RetryDecision:
        """Return the next action after attempt number ``attempt`` completed."""

        if attempt < 1:
            raise ValueError("attempt must be at least one")

        if failure_kind in _AUTH_FAILURES:
            if auth_supplied and not anonymous_retry_used:
                return RetryDecision(
                    retry=True,
                    use_anonymous=True,
                    reason="authentication failed; retrying once without authentication",
                )
            return self._stop("authentication failed and no anonymous retry is permitted")

        if failure_kind in _TRANSIENT:
            if attempt < self.max_attempts:
                return RetryDecision(
                    retry=True,
                    delay_seconds=self._backoff(attempt),
                    retry_same_engine=True,
                    reason=f"transient {failure_kind.value} failure",
                )
            return self._stop("transient retry limit reached")

        if failure_kind is FailureKind.EXTRACTOR:
            if alternate_available:
                return RetryDecision(
                    retry=True,
                    use_alternate_engine=True,
                    reason="extractor failed; trying the next compatible engine",
                )
            return self._stop("extractor failed and no alternate engine is available")

        if failure_kind in _STOP_IMMEDIATELY:
            return self._stop(f"{failure_kind.value} failures are not retryable")

        return self._stop("failure is not safely retryable")

    def _backoff(self, attempt: int) -> float:
        exponential = self.base_delay_seconds * (2.0 ** (attempt - 1))
        bounded = min(self.max_delay_seconds, exponential)
        sample = min(1.0, max(0.0, float(self._jitter())))
        return min(self.max_delay_seconds, bounded * (1.0 + self.jitter_ratio * sample))

    @staticmethod
    def _stop(reason: str) -> RetryDecision:
        return RetryDecision(retry=False, reason=reason)
