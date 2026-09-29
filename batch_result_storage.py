from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from config import (
    MAX_STORAGE_RETRY_BACKOFF_SECONDS,
    STORAGE_MAX_RETRIES,
    STORAGE_RETRY_BACKOFF_SECONDS,
)
from object_storage import ObjectStorage
from pdf_batching import PdfBatch

logger = logging.getLogger(__name__)
_KEY_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_TRANSIENT_S3_CODES = {
    "InternalError",
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceUnavailable",
    "SlowDown",
    "Throttling",
    "ThrottlingException",
}
_TRANSIENT_BOTOCORE_ERRORS = {
    "ConnectionClosedError",
    "ConnectTimeoutError",
    "EndpointConnectionError",
    "ReadTimeoutError",
}


@dataclass(frozen=True)
class BatchResultKeys:
    markdown_key: str
    json_key: str


def batch_result_keys(job_id: str, batch_id: str) -> BatchResultKeys:
    """Build deterministic, safe object keys for one job batch."""

    for value, label in ((job_id, "job_id"), (batch_id, "batch_id")):
        if not isinstance(value, str) or not _KEY_COMPONENT_RE.fullmatch(value):
            raise ValueError(
                f"{label} must contain only letters, digits, '_' or '-'."
            )

    prefix = f"jobs/{job_id}/batches/{batch_id}"
    return BatchResultKeys(
        markdown_key=f"{prefix}/result.md",
        json_key=f"{prefix}/result.json",
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    return str(value)


def _extract_result_json(result: Any) -> Any:
    value = getattr(result, "json", None)
    if callable(value):
        value = value()
    if value is None and isinstance(result, dict):
        value = result
    if value is None:
        value = str(result)
    return _json_safe(value)


def _extract_markdown(result: Any) -> str:
    value = getattr(result, "markdown", None)
    if value is None and isinstance(result, dict):
        value = result.get("markdown")
    if isinstance(value, dict):
        value = value.get("markdown_texts", value.get("text", ""))
    if isinstance(value, list):
        return "\n\n".join(str(part) for part in value if part)
    return value if isinstance(value, str) else ""


def serialize_batch_results(
    results: list[Any],
    batch: PdfBatch,
) -> tuple[bytes, bytes]:
    """Serialize page-level results to UTF-8 Markdown and JSON bytes."""

    if len(results) != batch.page_count:
        raise ValueError(
            f"Batch {batch.batch_id} has {len(results)} results; "
            f"expected {batch.page_count}."
        )

    markdown_parts = []
    json_results = []
    for page_number, result in zip(
        range(batch.page_start, batch.page_end + 1),
        results,
        strict=True,
    ):
        markdown = _extract_markdown(result)
        if markdown:
            markdown_parts.append(
                f"<!-- Page {page_number} -->\n\n{markdown}"
            )
        json_results.append(
            {
                "result": _extract_result_json(result),
                "page_numbers": [page_number],
            }
        )

    markdown_bytes = "\n\n".join(markdown_parts).encode("utf-8")
    json_bytes = json.dumps(
        json_results,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return markdown_bytes, json_bytes


def is_retryable_storage_error(error: Exception) -> bool:
    """Recognize network/transient S3 failures; do not retry client errors."""

    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True

    response = getattr(error, "response", None)
    if isinstance(response, dict):
        error_info = response.get("Error", {})
        metadata = response.get("ResponseMetadata", {})
        code = str(error_info.get("Code", ""))
        status_code = metadata.get("HTTPStatusCode")
        if code in _TRANSIENT_S3_CODES:
            return True
        if isinstance(status_code, int) and (
            status_code == 429 or status_code >= 500
        ):
            return True
        return False

    return (
        error.__class__.__module__.startswith("botocore.")
        and error.__class__.__name__ in _TRANSIENT_BOTOCORE_ERRORS
    )


def calculate_storage_backoff(
    attempt: int,
    base_seconds: int = STORAGE_RETRY_BACKOFF_SECONDS,
    max_seconds: int = MAX_STORAGE_RETRY_BACKOFF_SECONDS,
) -> int:
    """Calculate capped exponential backoff for a one-based failed attempt."""

    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("attempt must be a positive integer.")
    if base_seconds <= 0 or max_seconds <= 0:
        raise ValueError("storage backoff values must be greater than zero.")
    if base_seconds > max_seconds:
        raise ValueError("base_seconds cannot exceed max_seconds.")
    return min(base_seconds * (2 ** (attempt - 1)), max_seconds)


def _upload_with_retry(
    storage: ObjectStorage,
    key: str,
    data: bytes,
    content_type: str,
    *,
    max_retries: int,
    sleep: Callable[[float], None],
) -> None:
    total_attempts = max_retries + 1
    for attempt in range(1, total_attempts + 1):
        try:
            storage.upload_bytes(key, data, content_type)
            logger.info(
                "batch_result_upload status=completed key=%s attempt=%s/%s",
                key,
                attempt,
                total_attempts,
            )
            return
        except Exception as error:
            retryable = is_retryable_storage_error(error)
            if not retryable or attempt >= total_attempts:
                logger.error(
                    "batch_result_upload status=failed key=%s attempt=%s/%s "
                    "retryable=%s",
                    key,
                    attempt,
                    total_attempts,
                    retryable,
                )
                raise

            delay = calculate_storage_backoff(attempt)
            logger.warning(
                "batch_result_upload status=retrying key=%s attempt=%s/%s "
                "backoff_seconds=%s",
                key,
                attempt,
                total_attempts,
                delay,
            )
            sleep(delay)


def upload_batch_results(
    storage: ObjectStorage,
    job_id: str,
    batch: PdfBatch,
    results: list[Any],
    *,
    max_retries: int = STORAGE_MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> BatchResultKeys:
    """Serialize and upload Markdown and JSON results for one OCR batch.

    Uploads use deterministic object keys. Repeating an upload safely
    overwrites the same object, which makes transient retries idempotent.
    """

    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise ValueError("max_retries must be an integer.")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative.")

    keys = batch_result_keys(job_id, batch.batch_id)
    markdown_bytes, json_bytes = serialize_batch_results(results, batch)
    _upload_with_retry(
        storage,
        keys.markdown_key,
        markdown_bytes,
        "text/markdown; charset=utf-8",
        max_retries=max_retries,
        sleep=sleep,
    )
    _upload_with_retry(
        storage,
        keys.json_key,
        json_bytes,
        "application/json",
        max_retries=max_retries,
        sleep=sleep,
    )
    return keys


__all__ = [
    "BatchResultKeys",
    "batch_result_keys",
    "calculate_storage_backoff",
    "is_retryable_storage_error",
    "serialize_batch_results",
    "upload_batch_results",
]
