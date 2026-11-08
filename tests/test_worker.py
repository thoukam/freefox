"""Error policy of the upload worker: each backend outcome maps to one queue decision."""

from types import SimpleNamespace

import pytest

from freefox.backends import (
    AuthenticationBackendError,
    ConflictBackendError,
    QuotaBackendError,
    TransientBackendError,
)
from freefox.queue import Status, UploadQueue
from freefox.worker import UploadWorkerPool


def _config(**overrides):
    values = dict(
        workers=1,
        chunk_size=1024 * 1024,
        max_retries=3,
        retry_backoff_base=2.0,
        retry_backoff_max=10.0,
        quota_retry_delay=60.0,
        transient_retry_delay=30.0,
        verify_blake3=True,
        deduplicate_by_hash=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeBackend:
    def __init__(self, error=None, duplicate=False):
        self.error = error
        self.duplicate = duplicate
        self.uploads = 0

    def exists(self, remote_path):
        return False

    def find_duplicate(self, remote_path, blake3_digest, size_bytes):
        return self.duplicate

    def upload(self, local_path, remote_path, **kwargs):
        self.uploads += 1
        if self.error:
            raise self.error
        return remote_path


@pytest.fixture
def queued(tmp_path):
    bag = tmp_path / "run.mcap"
    bag.write_bytes(b"rosbag")
    queue = UploadQueue(tmp_path / "q.db")
    entry = queue.add(bag, "robot/run.mcap", backend="rsync", destination={})
    return bag, queue, queue.next_ready() or entry


def _process(queue, entry, backend, delete_after=False, **config):
    pool = UploadWorkerPool(
        queue=queue, backend=backend, config=_config(**config), delete_after=delete_after
    )
    pool._process(entry)
    return queue.get(entry.id)


def test_success_marks_done_and_stores_fingerprint(queued):
    bag, queue, entry = queued
    result = _process(queue, entry, FakeBackend())
    assert result.status == Status.DONE
    assert result.blake3_digest and result.size_bytes == bag.stat().st_size


def test_duplicate_is_done_without_upload_and_keeps_local_file(queued):
    bag, queue, entry = queued
    backend = FakeBackend(duplicate=True)
    result = _process(queue, entry, backend, delete_after=True)
    assert result.status == Status.DONE and backend.uploads == 0 and bag.exists()


def test_delete_after_upload_removes_local_file(queued):
    bag, queue, entry = queued
    assert _process(queue, entry, FakeBackend(), delete_after=True).status == Status.DONE
    assert not bag.exists()


@pytest.mark.parametrize(
    ("error", "status", "retries"),
    [
        (ConflictBackendError("different content"), Status.CONFLICT, 0),
        (QuotaBackendError("slow down"), Status.QUEUED, 0),
        (TransientBackendError("timeout"), Status.QUEUED, 0),
        (AuthenticationBackendError("denied"), Status.FAILED, 1),
        (RuntimeError("boom"), Status.QUEUED, 1),
        (RuntimeError("Connection reset by peer"), Status.QUEUED, 0),
    ],
)
def test_errors_map_to_queue_decisions(queued, error, status, retries):
    _, queue, entry = queued
    result = _process(queue, entry, FakeBackend(error=error))
    assert result.status == status and result.retries == retries


def test_missing_local_file_fails_without_retry(queued):
    bag, queue, entry = queued
    bag.unlink()
    assert _process(queue, entry, FakeBackend()).status == Status.FAILED


def test_backend_setup_error_does_not_kill_the_worker(queued):
    _, queue, entry = queued

    class BrokenRegistry:
        def get(self, backend, destination):
            raise ValueError("invalid S3 configuration")

    pool = UploadWorkerPool(queue=queue, registry=BrokenRegistry(), config=_config())
    pool._process(entry)  # must not raise: the thread would die silently
    result = queue.get(entry.id)
    assert result.status == Status.QUEUED and result.retries == 1
    assert "invalid S3 configuration" in result.error
