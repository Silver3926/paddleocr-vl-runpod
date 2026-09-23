from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from config import (
    BATCH_RETRY_BACKOFF_SECONDS,
    MAX_BATCH_RETRIES,
    MAX_BATCH_RETRY_BACKOFF_SECONDS,
)


class BatchStatus(StrEnum):
    """Internal lifecycle states for one PDF batch."""

    PENDING = "pending"
    PROCESSING = "processing"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class BatchErrorClass(StrEnum):
    """Retry policy classification for a batch exception."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class BatchProcessingError(Exception):
    """Base exception for errors raised while processing a batch."""


class BatchTransientError(BatchProcessingError):
    """An error that may succeed when the batch is retried."""


class BatchPermanentError(BatchProcessingError):
    """An error that should not be retried."""


class BatchTimeoutError(BatchProcessingError):
    """Raised when a batch exceeds its configured duration."""


@dataclass
class BatchExecutionStatus:
    """In-memory status for one batch execution."""

    batch_id: str
    page_start: int
    page_end: int
    status: BatchStatus = BatchStatus.PENDING
    attempts: int = 0
    error_class: BatchErrorClass | None = None
    error_message: str | None = None
    duration_seconds: float | None = None

    @property
    def page_count(self) -> int:
        return self.page_end - self.page_start + 1


def classify_batch_error(error: Exception) -> BatchErrorClass:
    """Classify an exception before deciding whether to retry it."""

    if isinstance(error, BatchTimeoutError):
        return BatchErrorClass.TIMEOUT
    if isinstance(error, BatchPermanentError):
        return BatchErrorClass.PERMANENT
    if isinstance(error, BatchTransientError):
        return BatchErrorClass.TRANSIENT
    if isinstance(error, (TimeoutError, ConnectionError)):
        return BatchErrorClass.TRANSIENT
    if isinstance(error, ValueError):
        return BatchErrorClass.PERMANENT
    return BatchErrorClass.UNKNOWN


def is_retryable(error_class: BatchErrorClass) -> bool:
    """Return whether the classification is eligible for retry."""

    return error_class in {
        BatchErrorClass.TRANSIENT,
        BatchErrorClass.TIMEOUT,
    }


def calculate_backoff(
    attempt: int,
    base_seconds: int = BATCH_RETRY_BACKOFF_SECONDS,
    max_seconds: int = MAX_BATCH_RETRY_BACKOFF_SECONDS,
) -> int:
    """Calculate capped exponential backoff for a one-based attempt."""

    if isinstance(attempt, bool) or not isinstance(attempt, int):
        raise ValueError("attempt must be an integer.")
    if attempt < 1:
        raise ValueError("attempt must be greater than zero.")
    if base_seconds < 1 or max_seconds < 1:
        raise ValueError("backoff values must be greater than zero.")
    if base_seconds > max_seconds:
        raise ValueError("base_seconds cannot exceed max_seconds.")

    return min(
        base_seconds * (2 ** (attempt - 1)),
        max_seconds,
    )


def new_batch_status(batch: Any) -> BatchExecutionStatus:
    """Create an internal status object from a PdfBatch-like value."""

    return BatchExecutionStatus(
        batch_id=batch.batch_id,
        page_start=batch.page_start,
        page_end=batch.page_end,
    )


__all__ = [
    "BatchErrorClass",
    "BatchExecutionStatus",
    "BatchPermanentError",
    "BatchProcessingError",
    "BatchStatus",
    "BatchTimeoutError",
    "BatchTransientError",
    "MAX_BATCH_RETRIES",
    "calculate_backoff",
    "classify_batch_error",
    "is_retryable",
    "new_batch_status",
]
