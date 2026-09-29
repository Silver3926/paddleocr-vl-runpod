import json

import pytest

from batch_result_storage import (
    batch_result_keys,
    calculate_storage_backoff,
    is_retryable_storage_error,
    serialize_batch_results,
    upload_batch_results,
)
from object_storage import FakeObjectStorage
from pdf_batching import PdfBatch


class ServiceError(Exception):
    def __init__(self, code, status_code):
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        }


class FlakyStorage(FakeObjectStorage):
    def __init__(self, failures):
        super().__init__()
        self.failures = list(failures)
        self.attempted_keys = []

    def upload_bytes(self, key, data, content_type):
        self.attempted_keys.append(key)
        if self.failures:
            outcome = self.failures.pop(0)
            if outcome is not None:
                raise outcome
        super().upload_bytes(key, data, content_type)


def test_batch_result_keys_follow_job_batch_layout():
    keys = batch_result_keys("job-123", "batch-0002")

    assert keys.markdown_key == (
        "jobs/job-123/batches/batch-0002/result.md"
    )
    assert keys.json_key == "jobs/job-123/batches/batch-0002/result.json"


@pytest.mark.parametrize("job_id,batch_id", [("../escape", "batch-1"), ("job", "../escape")])
def test_batch_result_keys_reject_unsafe_components(job_id, batch_id):
    with pytest.raises(ValueError):
        batch_result_keys(job_id, batch_id)


def test_serialize_batch_results_keeps_page_numbers_and_utf8():
    batch = PdfBatch("batch-0001", 4, 5)
    markdown_bytes, json_bytes = serialize_batch_results(
        [
            {"markdown": "Résumé page 4", "json": {"text": "résumé"}},
            {"markdown": "Page 5", "json": {"text": "second"}},
        ],
        batch,
    )

    markdown = markdown_bytes.decode("utf-8")
    payload = json.loads(json_bytes)

    assert "<!-- Page 4 -->" in markdown
    assert "Résumé page 4" in markdown
    assert "<!-- Page 5 -->" in markdown
    assert payload == [
        {"result": {"text": "résumé"}, "page_numbers": [4]},
        {"result": {"text": "second"}, "page_numbers": [5]},
    ]


def test_serialize_batch_results_rejects_page_count_mismatch():
    with pytest.raises(ValueError, match="expected 2"):
        serialize_batch_results(
            [{"markdown": "only one"}],
            PdfBatch("batch-0001", 1, 2),
        )


def test_upload_batch_results_writes_markdown_and_json():
    storage = FakeObjectStorage()
    batch = PdfBatch("batch-0001", 1, 1)

    keys = upload_batch_results(
        storage,
        "job-1",
        batch,
        [{"markdown": "OCR output", "json": {"text": "OCR output"}}],
    )

    assert storage.download_bytes(keys.markdown_key) == (
        b"<!-- Page 1 -->\n\nOCR output"
    )
    assert json.loads(storage.download_bytes(keys.json_key)) == [
        {"result": {"text": "OCR output"}, "page_numbers": [1]}
    ]
    assert storage.objects[keys.markdown_key].content_type.startswith(
        "text/markdown"
    )
    assert storage.objects[keys.json_key].content_type == "application/json"


def test_upload_retries_transient_storage_error_with_backoff():
    storage = FlakyStorage([TimeoutError("temporary"), None, None])
    sleeps = []
    batch = PdfBatch("batch-0001", 1, 1)

    keys = upload_batch_results(
        storage,
        "job-1",
        batch,
        [{"markdown": "output"}],
        max_retries=2,
        sleep=sleeps.append,
    )

    assert sleeps == [2]
    assert storage.attempted_keys == [
        keys.markdown_key,
        keys.markdown_key,
        keys.json_key,
    ]
    assert storage.object_exists(keys.markdown_key)
    assert storage.object_exists(keys.json_key)


def test_upload_does_not_retry_permanent_storage_error():
    storage = FlakyStorage([ServiceError("AccessDenied", 403)])
    sleeps = []

    with pytest.raises(ServiceError, match="AccessDenied"):
        upload_batch_results(
            storage,
            "job-1",
            PdfBatch("batch-0001", 1, 1),
            [{"markdown": "output"}],
            max_retries=3,
            sleep=sleeps.append,
        )

    assert len(storage.attempted_keys) == 1
    assert sleeps == []


def test_upload_stops_after_retry_budget():
    storage = FlakyStorage([
        TimeoutError("network 1"),
        TimeoutError("network 2"),
        TimeoutError("network 3"),
    ])
    sleeps = []

    with pytest.raises(TimeoutError, match="network 3"):
        upload_batch_results(
            storage,
            "job-1",
            PdfBatch("batch-0001", 1, 1),
            [{"markdown": "output"}],
            max_retries=2,
            sleep=sleeps.append,
        )

    assert len(storage.attempted_keys) == 3
    assert sleeps == [2, 4]


def test_storage_error_retry_classification():
    assert is_retryable_storage_error(TimeoutError())
    assert is_retryable_storage_error(ConnectionError())
    assert is_retryable_storage_error(ServiceError("SlowDown", 503))
    assert is_retryable_storage_error(ServiceError("InternalError", 500))
    assert not is_retryable_storage_error(ServiceError("AccessDenied", 403))
    assert not is_retryable_storage_error(ValueError("invalid key"))


def test_storage_backoff_is_exponential_and_capped():
    assert [
        calculate_storage_backoff(attempt, base_seconds=2, max_seconds=5)
        for attempt in range(1, 5)
    ] == [2, 4, 5, 5]
