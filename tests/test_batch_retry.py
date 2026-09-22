import pytest

from batch_retry import (
    BatchErrorClass,
    BatchExecutionStatus,
    BatchPermanentError,
    BatchStatus,
    BatchTransientError,
    calculate_backoff,
    classify_batch_error,
    is_retryable,
    new_batch_status,
)
from pdf_batching import PdfBatch


def test_new_batch_status_starts_pending():
    status = new_batch_status(PdfBatch("batch-0002", 6, 10))

    assert isinstance(status, BatchExecutionStatus)
    assert status.batch_id == "batch-0002"
    assert status.page_start == 6
    assert status.page_end == 10
    assert status.page_count == 5
    assert status.status is BatchStatus.PENDING
    assert status.attempts == 0


def test_classify_explicit_transient_error():
    error_class = classify_batch_error(BatchTransientError("temporary"))

    assert error_class is BatchErrorClass.TRANSIENT
    assert is_retryable(error_class) is True


def test_classify_explicit_permanent_error():
    error_class = classify_batch_error(BatchPermanentError("invalid"))

    assert error_class is BatchErrorClass.PERMANENT
    assert is_retryable(error_class) is False


def test_classify_builtin_errors():
    assert classify_batch_error(TimeoutError()) is BatchErrorClass.TRANSIENT
    assert classify_batch_error(ConnectionError()) is BatchErrorClass.TRANSIENT
    assert classify_batch_error(ValueError()) is BatchErrorClass.PERMANENT
    assert classify_batch_error(RuntimeError()) is BatchErrorClass.UNKNOWN


def test_backoff_is_exponential_and_capped():
    assert [
        calculate_backoff(attempt, base_seconds=2, max_seconds=10)
        for attempt in range(1, 6)
    ] == [2, 4, 8, 10, 10]


def test_backoff_rejects_invalid_attempt():
    with pytest.raises(ValueError, match="attempt"):
        calculate_backoff(0)

    with pytest.raises(ValueError, match="attempt"):
        calculate_backoff(True)


def test_backoff_rejects_invalid_limits():
    with pytest.raises(ValueError, match="backoff"):
        calculate_backoff(1, base_seconds=0, max_seconds=10)

    with pytest.raises(ValueError, match="cannot exceed"):
        calculate_backoff(1, base_seconds=10, max_seconds=2)
