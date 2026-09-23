from pathlib import Path

import pytest

import batch_execution
from batch_execution import (
    BatchExecutionFailure,
    execute_batch_once,
    execute_batch_with_retry,
)
from batch_retry import (
    BatchPermanentError,
    BatchStatus,
    BatchTimeoutError,
    BatchTransientError,
)
from pdf_batching import PdfBatch


class FakePipeline:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def predict(self, input):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def fake_split(source_pdf, destination_pdf, batch):
    Path(destination_pdf).write_bytes(b"batch")


def test_execute_batch_once_splits_and_validates_result_count(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_execution, "split_pdf_batch", fake_split)
    pipeline = FakePipeline([["page-1", "page-2"]])
    batch = PdfBatch("batch-0001", 1, 2)
    path = tmp_path / "batch-0001.pdf"

    results = execute_batch_once(
        pipeline_instance=pipeline,
        source_document=object(),
        batch=batch,
        batch_path=path,
    )

    assert results == ["page-1", "page-2"]
    assert pipeline.calls == 1
    assert path.exists()


def test_execute_batch_retries_transient_error(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_execution, "split_pdf_batch", fake_split)
    pipeline = FakePipeline([
        BatchTransientError("temporary failure"),
        ["page-1"],
    ])
    sleeps = []
    batch = PdfBatch("batch-0001", 1, 1)

    results, status = execute_batch_with_retry(
        pipeline_instance=pipeline,
        source_document=object(),
        batch=batch,
        batch_path=tmp_path / "batch-0001.pdf",
        max_retries=2,
        sleep=sleeps.append,
        clock=lambda: 0.0,
    )

    assert results == ["page-1"]
    assert pipeline.calls == 2
    assert sleeps == [2]
    assert status.status is BatchStatus.COMPLETED
    assert status.attempts == 2
    assert status.error_class is None
    assert status.duration_seconds == 0.0
    assert list(tmp_path.iterdir()) == []


def test_execute_batch_does_not_retry_permanent_error(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(batch_execution, "split_pdf_batch", fake_split)
    pipeline = FakePipeline([BatchPermanentError("invalid batch")])
    sleeps = []
    batch = PdfBatch("batch-0001", 1, 1)

    with pytest.raises(BatchExecutionFailure) as caught:
        execute_batch_with_retry(
            pipeline_instance=pipeline,
            source_document=object(),
            batch=batch,
            batch_path=tmp_path / "batch-0001.pdf",
            max_retries=2,
            sleep=sleeps.append,
            clock=lambda: 0.0,
        )

    assert pipeline.calls == 1
    assert sleeps == []
    assert caught.value.status.status is BatchStatus.FAILED
    assert caught.value.status.attempts == 1
    assert list(tmp_path.iterdir()) == []


def test_execute_batch_stops_after_retry_budget(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(batch_execution, "split_pdf_batch", fake_split)
    pipeline = FakePipeline([
        BatchTransientError("temporary 1"),
        BatchTransientError("temporary 2"),
        BatchTransientError("temporary 3"),
    ])
    sleeps = []
    batch = PdfBatch("batch-0001", 1, 1)

    with pytest.raises(BatchExecutionFailure) as caught:
        execute_batch_with_retry(
            pipeline_instance=pipeline,
            source_document=object(),
            batch=batch,
            batch_path=tmp_path / "batch-0001.pdf",
            max_retries=2,
            sleep=sleeps.append,
            clock=lambda: 0.0,
        )

    assert pipeline.calls == 3
    assert sleeps == [2, 4]
    assert caught.value.status.status is BatchStatus.FAILED
    assert caught.value.status.attempts == 3
    assert list(tmp_path.iterdir()) == []


def test_execute_batch_rejects_wrong_result_count(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(batch_execution, "split_pdf_batch", fake_split)
    pipeline = FakePipeline([["only-one-result"]])
    batch = PdfBatch("batch-0001", 1, 2)

    with pytest.raises(BatchExecutionFailure) as caught:
        execute_batch_with_retry(
            pipeline_instance=pipeline,
            source_document=object(),
            batch=batch,
            batch_path=tmp_path / "batch-0001.pdf",
            max_retries=2,
            sleep=lambda _: None,
            clock=lambda: 0.0,
        )

    assert pipeline.calls == 1
    assert caught.value.status.attempts == 1
    assert caught.value.status.error_message is not None


def test_execute_batch_marks_soft_timeout_and_cleans_artifact(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(batch_execution, "split_pdf_batch", fake_split)
    pipeline = FakePipeline([["page-1"]])
    clock_values = iter([0.0, 6.0])
    batch = PdfBatch("batch-0001", 1, 1)

    with pytest.raises(BatchExecutionFailure) as caught:
        execute_batch_with_retry(
            pipeline_instance=pipeline,
            source_document=object(),
            batch=batch,
            batch_path=tmp_path / "batch-0001.pdf",
            max_retries=0,
            max_duration_seconds=5,
            sleep=lambda _: None,
            clock=lambda: next(clock_values),
        )

    assert isinstance(caught.value.__cause__, BatchTimeoutError)
    assert caught.value.status.status is BatchStatus.TIMED_OUT
    assert caught.value.status.attempts == 1
    assert caught.value.status.duration_seconds == 6.0
    assert list(tmp_path.iterdir()) == []


def test_execute_batch_emits_progress_transitions(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_execution, "split_pdf_batch", fake_split)
    pipeline = FakePipeline([
        BatchTransientError("temporary failure"),
        ["page-1"],
    ])
    transitions = []
    batch = PdfBatch("batch-0001", 1, 1)

    execute_batch_with_retry(
        pipeline_instance=pipeline,
        source_document=object(),
        batch=batch,
        batch_path=tmp_path / "batch-0001.pdf",
        max_retries=1,
        sleep=lambda _: None,
        clock=lambda: 0.0,
        progress=lambda status: transitions.append(status.status),
    )

    assert transitions == [
        BatchStatus.PROCESSING,
        BatchStatus.RETRYING,
        BatchStatus.PROCESSING,
        BatchStatus.COMPLETED,
    ]
