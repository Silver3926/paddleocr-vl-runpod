import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from batch_retry import (
    MAX_BATCH_RETRIES,
    BatchErrorClass,
    BatchExecutionStatus,
    BatchProcessingError,
    BatchStatus,
    BatchTimeoutError,
    BatchTransientError,
    calculate_backoff,
    classify_batch_error,
    is_retryable,
    new_batch_status,
)
from config import MAX_BATCH_DURATION_SECONDS
from pdf_batching import PdfBatch
from pdf_processor import split_pdf_batch

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[BatchExecutionStatus], None]


class BatchExecutionFailure(BatchProcessingError):
    """Raised when a batch cannot be completed within its retry policy."""

    def __init__(
        self,
        message: str,
        status: BatchExecutionStatus,
    ) -> None:
        super().__init__(message)
        self.status = status


def execute_batch_once(
    pipeline_instance: Any,
    source_document: Any,
    batch: PdfBatch,
    batch_path: Path,
) -> list[Any]:
    """Split and OCR one batch exactly once."""

    split_pdf_batch(
        source_pdf=source_document,
        destination_pdf=batch_path,
        batch=batch,
    )

    results = list(
        pipeline_instance.predict(input=str(batch_path))
    )
    if not results:
        raise BatchTransientError(
            f"PaddleOCR-VL returned no results for {batch.batch_id}."
        )
    if len(results) != batch.page_count:
        raise ValueError(
            f"PaddleOCR-VL returned {len(results)} results for "
            f"{batch.batch_id}, expected {batch.page_count}."
        )
    return results


def _emit_progress(
    status: BatchExecutionStatus,
    progress: ProgressCallback | None,
) -> None:
    logger.info(
        "batch_status=%s batch_id=%s attempt=%s "
        "duration_seconds=%s",
        status.status,
        status.batch_id,
        status.attempts,
        status.duration_seconds,
    )
    if progress is not None:
        progress(replace(status))


def execute_batch_with_retry(
    pipeline_instance: Any,
    source_document: Any,
    batch: PdfBatch,
    batch_path: Path,
    max_retries: int = MAX_BATCH_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
    max_duration_seconds: int = MAX_BATCH_DURATION_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    progress: ProgressCallback | None = None,
) -> tuple[list[Any], BatchExecutionStatus]:
    """Execute one batch with retry, timeout measurement, and progress logs.

    ``max_retries`` counts retries after the initial attempt. The duration
    limit is a soft timeout: inference is allowed to return, then the result
    is rejected if the measured attempt duration exceeds the limit.
    """

    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise ValueError("max_retries must be an integer.")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative.")
    if (
        isinstance(max_duration_seconds, bool)
        or not isinstance(max_duration_seconds, int)
    ):
        raise ValueError("max_duration_seconds must be an integer.")
    if max_duration_seconds <= 0:
        raise ValueError("max_duration_seconds must be greater than zero.")

    status = new_batch_status(batch)
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        status.attempts = attempt
        status.status = BatchStatus.PROCESSING
        status.error_class = None
        status.error_message = None
        status.duration_seconds = None
        retry_delay = None
        started = clock()
        _emit_progress(status, progress)

        try:
            results = execute_batch_once(
                pipeline_instance=pipeline_instance,
                source_document=source_document,
                batch=batch,
                batch_path=batch_path,
            )
            elapsed = clock() - started
            status.duration_seconds = elapsed
            if elapsed > max_duration_seconds:
                raise BatchTimeoutError(
                    f"Batch {batch.batch_id} exceeded maximum duration "
                    f"of {max_duration_seconds} seconds."
                )

            status.status = BatchStatus.COMPLETED
            _emit_progress(status, progress)
            return results, status

        except Exception as error:
            if status.duration_seconds is None:
                status.duration_seconds = clock() - started
            error_class = classify_batch_error(error)
            status.error_class = error_class
            status.error_message = str(error)
            can_retry = (
                is_retryable(error_class)
                and attempt < total_attempts
            )

            if not can_retry:
                status.status = (
                    BatchStatus.TIMED_OUT
                    if error_class is BatchErrorClass.TIMEOUT
                    else BatchStatus.FAILED
                )
                _emit_progress(status, progress)
                logger.error(
                    "batch_status=%s batch_id=%s attempt=%s/%s "
                    "error_class=%s error=%s",
                    status.status,
                    batch.batch_id,
                    attempt,
                    total_attempts,
                    error_class,
                    error,
                )
                raise BatchExecutionFailure(
                    f"Batch {batch.batch_id} failed after "
                    f"{attempt} attempt(s): {error}",
                    status=status,
                ) from error

            status.status = BatchStatus.RETRYING
            retry_delay = calculate_backoff(attempt)
            _emit_progress(status, progress)
            logger.warning(
                "batch_status=retrying batch_id=%s attempt=%s/%s "
                "error_class=%s backoff_seconds=%s",
                batch.batch_id,
                attempt,
                total_attempts,
                error_class,
                retry_delay,
            )

        finally:
            batch_path.unlink(missing_ok=True)

        if retry_delay is not None:
            sleep(retry_delay)

    raise AssertionError("Batch retry loop exited unexpectedly.")


__all__ = [
    "BatchExecutionFailure",
    "ProgressCallback",
    "execute_batch_once",
    "execute_batch_with_retry",
]
