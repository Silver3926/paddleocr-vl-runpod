import logging
import time
from pathlib import Path
from typing import Any, Callable

from batch_retry import (
    MAX_BATCH_RETRIES,
    BatchErrorClass,
    BatchExecutionStatus,
    BatchProcessingError,
    BatchStatus,
    BatchTransientError,
    calculate_backoff,
    classify_batch_error,
    is_retryable,
    new_batch_status,
)
from pdf_batching import PdfBatch
from pdf_processor import split_pdf_batch

logger = logging.getLogger(__name__)


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


def execute_batch_with_retry(
    pipeline_instance: Any,
    source_document: Any,
    batch: PdfBatch,
    batch_path: Path,
    max_retries: int = MAX_BATCH_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[Any], BatchExecutionStatus]:
    """Execute one batch and retry only retryable failures.

    ``max_retries`` counts retries after the initial attempt. Therefore,
    ``max_retries=2`` permits at most three total executions.
    """

    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise ValueError("max_retries must be an integer.")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative.")

    status = new_batch_status(batch)
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        status.attempts = attempt
        status.status = BatchStatus.PROCESSING

        try:
            results = execute_batch_once(
                pipeline_instance=pipeline_instance,
                source_document=source_document,
                batch=batch,
                batch_path=batch_path,
            )
            status.status = BatchStatus.COMPLETED
            status.error_class = None
            status.error_message = None
            logger.info(
                "batch_status=completed batch_id=%s attempt=%s/%s",
                batch.batch_id,
                attempt,
                total_attempts,
            )
            return results, status

        except Exception as error:
            error_class = classify_batch_error(error)
            status.error_class = error_class
            status.error_message = str(error)
            can_retry = (
                is_retryable(error_class)
                and attempt < total_attempts
            )

            if not can_retry:
                status.status = BatchStatus.FAILED
                logger.error(
                    "batch_status=failed batch_id=%s attempt=%s/%s "
                    "error_class=%s error=%s",
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
            delay = calculate_backoff(attempt)
            logger.warning(
                "batch_status=retrying batch_id=%s attempt=%s/%s "
                "error_class=%s backoff_seconds=%s",
                batch.batch_id,
                attempt,
                total_attempts,
                error_class,
                delay,
            )
            sleep(delay)

        finally:
            batch_path.unlink(missing_ok=True)

    raise AssertionError("Batch retry loop exited unexpectedly.")


__all__ = [
    "BatchExecutionFailure",
    "execute_batch_once",
    "execute_batch_with_retry",
]
