"""Private storage abstraction with local and S3-compatible backends."""

from pathlib import Path
from typing import Protocol

from .config import settings


class StorageBackend(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            raise ValueError("Storage key escapes the configured storage directory")
        return candidate

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class S3Storage:
    def __init__(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("S3 storage requires the boto3 dependency") from exc
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=settings.s3_bucket, Key=key)
        return response["Body"].read()


def get_storage() -> StorageBackend:
    if settings.storage_backend.lower() == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("S3_STORAGE_BUCKET is required when STORAGE_BACKEND=s3")
        return S3Storage()
    return LocalStorage(settings.storage_dir)
