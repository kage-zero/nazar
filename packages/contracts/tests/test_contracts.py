import itertools
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from nazar_contracts import PIPELINE_STAGES, JobEvent, JobStatus, StageName, can_transition

events: TypeAdapter[JobEvent] = TypeAdapter(JobEvent)


def test_happy_path_walks_every_stage_in_order() -> None:
    path = [JobStatus.CREATED, JobStatus.VALIDATING, JobStatus.QUEUED]
    path += [JobStatus(s.value) for s in PIPELINE_STAGES] + [JobStatus.COMPLETED]
    for current, target in itertools.pairwise(path):
        assert can_transition(current, target), f"{current} -> {target}"


def test_optional_stage_can_be_skipped_but_not_reversed() -> None:
    assert can_transition(JobStatus.DYNAMIC_ANALYSIS, JobStatus.DENSE_RECONSTRUCTION)
    assert not can_transition(JobStatus.ANALYSIS, JobStatus.GEOMETRY)


def test_job_cannot_complete_before_final_stage() -> None:
    assert not can_transition(JobStatus.GEOMETRY, JobStatus.COMPLETED)
    assert not can_transition(JobStatus.QUEUED, JobStatus.COMPLETED)


def test_terminal_states_and_cancellation() -> None:
    assert can_transition(JobStatus.GEOMETRY, JobStatus.CANCEL_REQUESTED)
    assert can_transition(JobStatus.CANCEL_REQUESTED, JobStatus.CANCELLED)
    assert not can_transition(JobStatus.COMPLETED, JobStatus.FAILED)
    assert can_transition(JobStatus.FAILED, JobStatus.QUEUED)  # retry


def test_event_union_parses_by_discriminator() -> None:
    event = events.validate_python(
        {
            "job_id": "job_1",
            "seq": 3,
            "ts": datetime.now(UTC).isoformat(),
            "status": "preprocessing",
            "stage": "preprocessing",
            "type": "stage.progress",
            "data": {"message": "Scoring frames", "completed": 10, "total": 567, "unit": "frames"},
        }
    )
    assert event.type == "stage.progress"
    assert event.stage is StageName.PREPROCESSING


def test_event_rejects_unknown_fields_and_bad_seq() -> None:
    base = {
        "job_id": "job_1",
        "ts": datetime.now(UTC).isoformat(),
        "status": "queued",
        "type": "stage.started",
    }
    with pytest.raises(ValidationError):
        events.validate_python({**base, "seq": 0})
    with pytest.raises(ValidationError):
        events.validate_python({**base, "seq": 1, "percent": 50})
