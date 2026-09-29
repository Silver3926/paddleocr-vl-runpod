from io import BytesIO

import pytest

import object_storage
from object_storage import (
    FakeObjectStorage,
    ObjectStorage,
    S3ObjectStorage,
    create_s3_object_storage,
)


class FakeS3Client:
    def __init__(self):
        self.calls = []
        self.objects = {}
        self.head_error = None
        self.presigned_url = "https://s3.example.test/presigned"

    def put_object(self, **kwargs):
        self.calls.append(("put_object", kwargs))
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs["ContentType"],
        }

    def get_object(self, **kwargs):
        self.calls.append(("get_object", kwargs))
        item = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        return {"Body": BytesIO(item["Body"])}

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        if self.head_error:
            raise self.head_error
        if (kwargs["Bucket"], kwargs["Key"]) not in self.objects:
            raise S3Error("404")
        return {}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append(("generate_presigned_url", operation, Params, ExpiresIn))
        return self.presigned_url


class S3Error(Exception):
    def __init__(self, code, status_code=None):
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        }


def test_fake_storage_implements_object_storage_protocol():
    storage = FakeObjectStorage()

    assert isinstance(storage, ObjectStorage)


def test_fake_storage_upload_download_exists_and_url():
    storage = FakeObjectStorage(bucket="unit-test")
    storage.upload_bytes(
        "jobs/job-1/result.md",
        b"# OCR output",
        "text/markdown",
    )

    assert storage.object_exists("jobs/job-1/result.md") is True
    assert storage.download_bytes("jobs/job-1/result.md") == b"# OCR output"
    assert storage.objects["jobs/job-1/result.md"].content_type == "text/markdown"
    assert storage.get_url("jobs/job-1/result.md") == (
        "fake://unit-test/jobs/job-1/result.md"
    )


def test_fake_storage_reports_missing_object():
    storage = FakeObjectStorage()

    assert storage.object_exists("jobs/missing.json") is False
    with pytest.raises(FileNotFoundError, match="Object not found"):
        storage.download_bytes("jobs/missing.json")
    with pytest.raises(FileNotFoundError, match="Object not found"):
        storage.get_url("jobs/missing.json")


def test_s3_upload_download_and_presigned_url():
    client = FakeS3Client()
    storage = S3ObjectStorage(
        "ocr-results",
        client=client,
        region="us-west-2",
        presigned_url_ttl_seconds=900,
    )

    storage.upload_bytes("jobs/job-1/result.json", b'{"ok":true}', "application/json")

    assert storage.object_exists("jobs/job-1/result.json") is True
    assert storage.download_bytes("jobs/job-1/result.json") == b'{"ok":true}'
    assert storage.get_url("jobs/job-1/result.json") == client.presigned_url
    assert client.calls[0] == (
        "put_object",
        {
            "Bucket": "ocr-results",
            "Key": "jobs/job-1/result.json",
            "Body": b'{"ok":true}',
            "ContentType": "application/json",
        },
    )
    assert client.calls[-1] == (
        "generate_presigned_url",
        "get_object",
        {"Bucket": "ocr-results", "Key": "jobs/job-1/result.json"},
        900,
    )


def test_s3_object_exists_returns_false_for_not_found():
    storage = S3ObjectStorage("ocr-results", client=FakeS3Client())

    assert storage.object_exists("missing.json") is False


def test_s3_object_exists_propagates_non_not_found_errors():
    client = FakeS3Client()
    client.head_error = S3Error("AccessDenied", status_code=403)
    storage = S3ObjectStorage("ocr-results", client=client)

    with pytest.raises(S3Error, match="AccessDenied"):
        storage.object_exists("private.json")


def test_s3_download_closes_response_body():
    class ClosableBody(BytesIO):
        was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    body = ClosableBody(b"payload")

    class BodyClient(FakeS3Client):
        def get_object(self, **kwargs):
            return {"Body": body}

    storage = S3ObjectStorage("ocr-results", client=BodyClient())

    assert storage.download_bytes("result.bin") == b"payload"
    assert body.was_closed is True


@pytest.mark.parametrize(
    "key",
    ["", "   ", "/absolute/key", "jobs/../secret", "jobs/./file", "bad\\key"],
)
def test_storage_rejects_unsafe_object_keys(key):
    storage = FakeObjectStorage()

    with pytest.raises(ValueError):
        storage.object_exists(key)


def test_storage_rejects_invalid_upload_data():
    storage = FakeObjectStorage()

    with pytest.raises(TypeError, match="bytes"):
        storage.upload_bytes("result.bin", "not bytes", "application/octet-stream")
    with pytest.raises(ValueError, match="content_type"):
        storage.upload_bytes("result.bin", b"data", " ")


def test_s3_storage_validates_constructor_options():
    with pytest.raises(ValueError, match="bucket"):
        S3ObjectStorage(" ", client=FakeS3Client())
    with pytest.raises(ValueError, match="region"):
        S3ObjectStorage("bucket", client=FakeS3Client(), region=" ")
    with pytest.raises(ValueError, match="positive integer"):
        S3ObjectStorage(
            "bucket",
            client=FakeS3Client(),
            presigned_url_ttl_seconds=0,
        )
    with pytest.raises(ValueError, match="configured together"):
        S3ObjectStorage(
            "bucket",
            client=FakeS3Client(),
            access_key_id="only-access-key",
        )


def test_storage_factory_requires_enabled_and_bucket(monkeypatch):
    monkeypatch.setattr(object_storage, "STORAGE_ENABLED", False)
    with pytest.raises(RuntimeError, match="disabled"):
        create_s3_object_storage()

    monkeypatch.setattr(object_storage, "STORAGE_ENABLED", True)
    monkeypatch.setattr(object_storage, "STORAGE_BUCKET", None)
    with pytest.raises(ValueError, match="STORAGE_BUCKET"):
        create_s3_object_storage()
