from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import md5

import pytest


class FakeClientError(Exception):
    def __init__(self, code: str, message: str = "fake error", status: int = 400):
        self.response = {"Error": {"Code": code, "Message": message}, "ResponseMetadata": {"HTTPStatusCode": status}}
        super().__init__(message)


@dataclass
class FakeS3Client:
    objects: dict[tuple[str, str], dict] = field(default_factory=dict)
    uploads: dict[str, dict] = field(default_factory=dict)
    calls: list[tuple[str, dict]] = field(default_factory=list)
    failures: dict[str, Exception] = field(default_factory=dict)
    _counter: int = 0

    def _call(self, name, kwargs):
        self.calls.append((name, dict(kwargs)))
        if name in self.failures:
            raise self.failures.pop(name)

    def head_object(self, **kwargs):
        self._call("head_object", kwargs)
        try:
            return self.objects[(kwargs["Bucket"], kwargs["Key"])]
        except KeyError as exc:
            raise FakeClientError("404", "not found", 404) from exc

    def put_object(self, **kwargs):
        self._call("put_object", kwargs)
        body = kwargs["Body"].read() if hasattr(kwargs["Body"], "read") else kwargs["Body"]
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {"ContentLength": len(body), "Metadata": kwargs.get("Metadata", {}), "Body": body}
        return {"ETag": md5(body, usedforsecurity=False).hexdigest()}

    def create_multipart_upload(self, **kwargs):
        self._call("create_multipart_upload", kwargs)
        self._counter += 1
        upload_id = f"upload-{self._counter}"
        self.uploads[upload_id] = {"request": kwargs, "parts": {}}
        return {"UploadId": upload_id}

    def upload_part(self, **kwargs):
        self._call("upload_part", kwargs)
        body = kwargs["Body"].read() if hasattr(kwargs["Body"], "read") else kwargs["Body"]
        etag = md5(body, usedforsecurity=False).hexdigest()
        self.uploads[kwargs["UploadId"]]["parts"][kwargs["PartNumber"]] = (etag, body)
        return {"ETag": etag}

    def list_parts(self, **kwargs):
        self._call("list_parts", kwargs)
        if kwargs["UploadId"] not in self.uploads:
            raise FakeClientError("NoSuchUpload", "missing", 404)
        parts = self.uploads[kwargs["UploadId"]]["parts"]
        return {"Parts": [{"PartNumber": n, "ETag": e, "Size": len(b)} for n, (e, b) in sorted(parts.items())]}

    def complete_multipart_upload(self, **kwargs):
        self._call("complete_multipart_upload", kwargs)
        upload = self.uploads.pop(kwargs["UploadId"])
        body = b"".join(upload["parts"][p["PartNumber"]][1] for p in kwargs["MultipartUpload"]["Parts"])
        request = upload["request"]
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {"ContentLength": len(body), "Metadata": request.get("Metadata", {}), "Body": body}
        return {"ETag": "multipart"}

    def abort_multipart_upload(self, **kwargs):
        self._call("abort_multipart_upload", kwargs)
        self.uploads.pop(kwargs["UploadId"], None)


@pytest.fixture
def fake_s3_client():
    return FakeS3Client()
