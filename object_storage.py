from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

from config import (
    MAX_S3_PRESIGNED_URL_TTL_SECONDS,
    STORAGE_ACCESS_KEY_ID,
    STORAGE_BUCKET,
    STORAGE_ENABLED,
    STORAGE_ENDPOINT_URL,
    STORAGE_PRESIGNED_URL_TTL_SECONDS,
    STORAGE_REGION,
    STORAGE_SECRET_ACCESS_KEY,
)


@runtime_checkable
class ObjectStorage(Protocol):
    """Minimal object-storage interface used by the worker."""

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> None:
        """Upload bytes and their media type to an object key."""
        ...

    def download_bytes(self, key: str) -> bytes:
        """Download the complete contents of an object."""
        ...

    def object_exists(self, key: str) -> bool:
        """Return whether the object exists, propagating other storage errors."""
        ...

    def get_url(self, key: str) -> str:
        """Return a temporary URL for reading an object."""
        ...


def _validate_object_key(key: str) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Object key must be a non-empty string.")
    normalized = key.strip()
    if normalized.startswith("/") or "\\" in normalized:
        raise ValueError("Object key must be a relative POSIX-style key.")
    if any(part in {".", ".."} for part in normalized.split("/")):
        raise ValueError("Object key cannot contain '.' or '..' segments.")
    return normalized


def _validate_upload(data: bytes, content_type: str) -> None:
    if not isinstance(data, bytes):
        raise TypeError("Object data must be bytes.")
    if not isinstance(content_type, str) or not content_type.strip():
        raise ValueError("content_type must be a non-empty string.")


class S3ObjectStorage:
    """S3-compatible object storage backed by boto3.

    ``client`` can be injected in tests. When omitted, boto3 is imported and
    configured lazily, keeping the storage dependency out of inline-only use.
    """

    def __init__(
        self,
        bucket: str,
        *,
        client: Any | None = None,
        region: str = STORAGE_REGION,
        endpoint_url: str | None = STORAGE_ENDPOINT_URL,
        access_key_id: str | None = STORAGE_ACCESS_KEY_ID,
        secret_access_key: str | None = STORAGE_SECRET_ACCESS_KEY,
        presigned_url_ttl_seconds: int = STORAGE_PRESIGNED_URL_TTL_SECONDS,
    ) -> None:
        if not isinstance(bucket, str) or not bucket.strip():
            raise ValueError("S3 bucket must be a non-empty string.")
        if not isinstance(region, str) or not region.strip():
            raise ValueError("S3 region must be a non-empty string.")
        if (
            isinstance(presigned_url_ttl_seconds, bool)
            or not isinstance(presigned_url_ttl_seconds, int)
            or not 1
            <= presigned_url_ttl_seconds
            <= MAX_S3_PRESIGNED_URL_TTL_SECONDS
        ):
            raise ValueError(
                "presigned_url_ttl_seconds must be between 1 and "
                f"{MAX_S3_PRESIGNED_URL_TTL_SECONDS}."
            )
        if bool(access_key_id) != bool(secret_access_key):
            raise ValueError(
                "access_key_id and secret_access_key must be configured together."
            )

        self.bucket = bucket.strip()
        self.region = region.strip()
        self.endpoint_url = endpoint_url.strip() if endpoint_url else None
        self.presigned_url_ttl_seconds = presigned_url_ttl_seconds
        self.client = (
            client
            if client is not None
            else self._create_client(
                region=self.region,
                endpoint_url=self.endpoint_url,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
            )
        )

    @staticmethod
    def _create_client(
        *,
        region: str,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
    ) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required to use S3 object storage."
            ) from exc

        client_options: dict[str, Any] = {"region_name": region}
        if endpoint_url:
            client_options["endpoint_url"] = endpoint_url
        if access_key_id and secret_access_key:
            client_options["aws_access_key_id"] = access_key_id
            client_options["aws_secret_access_key"] = secret_access_key
        return boto3.client("s3", **client_options)

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> None:
        key = _validate_object_key(key)
        _validate_upload(data, content_type)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type.strip(),
        )

    def download_bytes(self, key: str) -> bytes:
        key = _validate_object_key(key)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            data = body.read()
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
        if not isinstance(data, bytes):
            raise TypeError("S3 object body did not return bytes.")
        return data

    def object_exists(self, key: str) -> bool:
        key = _validate_object_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            response = getattr(exc, "response", None)
            if isinstance(response, dict):
                error = response.get("Error", {})
                metadata = response.get("ResponseMetadata", {})
                code = str(error.get("Code", ""))
                status_code = metadata.get("HTTPStatusCode")
                if code in {"404", "NoSuchKey", "NotFound"} or status_code == 404:
                    return False
            raise
        return True

    def get_url(self, key: str) -> str:
        key = _validate_object_key(key)
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.presigned_url_ttl_seconds,
        )


def create_s3_object_storage() -> S3ObjectStorage:
    """Construct configured S3 storage or fail with a useful configuration error."""

    if not STORAGE_ENABLED:
        raise RuntimeError(
            "Object storage is disabled; set STORAGE_ENABLED=true to enable it."
        )
    if not STORAGE_BUCKET:
        raise ValueError("STORAGE_BUCKET is required when storage is enabled.")
    return S3ObjectStorage(
        bucket=STORAGE_BUCKET,
        region=STORAGE_REGION,
        endpoint_url=STORAGE_ENDPOINT_URL,
        access_key_id=STORAGE_ACCESS_KEY_ID,
        secret_access_key=STORAGE_SECRET_ACCESS_KEY,
        presigned_url_ttl_seconds=STORAGE_PRESIGNED_URL_TTL_SECONDS,
    )


@dataclass(frozen=True)
class StoredObject:
    data: bytes
    content_type: str


class FakeObjectStorage:
    """In-memory ObjectStorage implementation for unit tests and local flows."""

    def __init__(self, bucket: str = "test-bucket") -> None:
        if not isinstance(bucket, str) or not bucket.strip():
            raise ValueError("Fake storage bucket must be a non-empty string.")
        self.bucket = bucket.strip()
        self.objects: dict[str, StoredObject] = {}

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> None:
        key = _validate_object_key(key)
        _validate_upload(data, content_type)
        self.objects[key] = StoredObject(
            data=data,
            content_type=content_type.strip(),
        )

    def download_bytes(self, key: str) -> bytes:
        key = _validate_object_key(key)
        try:
            return self.objects[key].data
        except KeyError as exc:
            raise FileNotFoundError(f"Object not found: {key}") from exc

    def object_exists(self, key: str) -> bool:
        key = _validate_object_key(key)
        return key in self.objects

    def get_url(self, key: str) -> str:
        key = _validate_object_key(key)
        if key not in self.objects:
            raise FileNotFoundError(f"Object not found: {key}")
        return f"fake://{self.bucket}/{quote(key, safe='/')}"


__all__ = [
    "FakeObjectStorage",
    "ObjectStorage",
    "S3ObjectStorage",
    "StoredObject",
    "create_s3_object_storage",
]
