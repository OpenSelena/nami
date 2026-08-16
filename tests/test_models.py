import json
from dataclasses import FrozenInstanceError

import pytest

from nami.models import (
    AttemptResult,
    BatchResult,
    FailureKind,
    MediaKind,
    OperationResult,
    Outcome,
    Platform,
    Target,
)


def _target() -> Target:
    return Target(
        original_url="https://instagram.com/NASA",
        canonical_url="https://www.instagram.com/NASA/",
        target_key="nasa",
        platform=Platform.INSTAGRAM,
        username="NASA",
        content_type="profile",
    )


def _result(outcome: Outcome, failure_kind: FailureKind | None = None) -> OperationResult:
    return OperationResult(
        target=_target(),
        media_kind=MediaKind.PHOTOS,
        outcome=outcome,
        failure_kind=failure_kind,
    )


def test_enums_are_string_enums() -> None:
    assert isinstance(Platform.X, str)
    assert Platform.X.value == "x"
    assert MediaKind.HIGHLIGHTS.value == "highlights"
    assert Outcome.UP_TO_DATE.value == "up_to_date"
    assert FailureKind.RATE_LIMIT.value == "rate_limit"


def test_models_are_immutable_and_json_safe() -> None:
    attempt = AttemptResult(
        outcome=Outcome.FAILED,
        extractor="gallery-dl",
        failure_kind=FailureKind.NETWORK,
        message="offline",
        return_code=1,
    )
    result = OperationResult(
        target=_target(),
        media_kind=MediaKind.VIDEOS,
        outcome=Outcome.PARTIAL,
        attempts=(attempt,),
        downloaded_count=2,
    )
    batch = BatchResult(operations=(result,))

    with pytest.raises(FrozenInstanceError):
        batch.results = ()  # type: ignore[misc]

    payload = batch.to_dict()
    assert payload["results"][0]["target"]["platform"] == "instagram"
    assert payload["results"][0]["attempts"][0]["failure_kind"] == "network"
    assert batch.operations == batch.results
    json.dumps(payload)


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        ([], 0),
        ([Outcome.DOWNLOADED], 0),
        ([Outcome.UP_TO_DATE, Outcome.DOWNLOADED], 0),
        ([Outcome.FAILED], 1),
        ([Outcome.INVALID], 2),
        ([Outcome.PARTIAL], 3),
        ([Outcome.UNSUPPORTED], 3),
        ([Outcome.FAILED, Outcome.DOWNLOADED], 3),
        ([Outcome.FAILED, Outcome.NO_RESULTS], 3),
        ([Outcome.NO_RESULTS, Outcome.NO_RESULTS], 4),
        ([Outcome.CANCELLED], 130),
        ([Outcome.CANCELLED, Outcome.INVALID], 130),
    ],
)
def test_batch_exit_codes(outcomes: list[Outcome], expected: int) -> None:
    assert BatchResult(tuple(_result(value) for value in outcomes)).exit_code() == expected


def test_config_failure_uses_invalid_config_exit_code() -> None:
    batch = BatchResult((_result(Outcome.FAILED, FailureKind.CONFIG),))
    assert batch.exit_code() == 2
