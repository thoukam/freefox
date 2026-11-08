import pytest

from freefox.backends import ConflictBackendError, Inspection, InvalidSessionError
from freefox.backends.s3 import S3Backend, effective_part_size
from freefox.config import S3Config
from freefox.queue import UploadQueue


def backend(client):
    return S3Backend(S3Config(bucket="bags"), client=client)


def test_put_confirm_deduplicate_and_conflict(tmp_path, fake_s3_client):
    f = tmp_path / "bag"
    f.write_bytes(b"hello")
    b = backend(fake_s3_client)
    progress = []
    b.upload(
        f,
        "r/bag",
        blake3_digest="digest",
        expected_size=5,
        progress_callback=lambda p, u: progress.append((p, u)),
    )
    assert b.inspect("r/bag", "digest", 5) == Inspection.IDENTICAL and progress[-1] == (100.0, 5)
    assert b.upload(f, "r/bag", blake3_digest="digest", expected_size=5).startswith("s3://")
    with pytest.raises(ConflictBackendError):
        b.upload(f, "r/bag", blake3_digest="other", expected_size=5)


def test_multipart_persists_and_completes(tmp_path, fake_s3_client):
    f = tmp_path / "large"
    f.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    q = UploadQueue(tmp_path / "q.db")
    e = q.add(f, "r/large", backend="s3", destination={"bucket": "bags"})
    q.mark_integrity(e.id, "d", f.stat().st_size)
    e = q.get(e.id)
    backend(fake_s3_client).upload_entry(e, q, f, 5 * 1024 * 1024)
    assert (
        q.get_multipart(e.id) is None
        and fake_s3_client.objects[("bags", "r/large")]["ContentLength"] == f.stat().st_size
    )


def test_part_size_limit():
    assert effective_part_size(5 * 1024**4, 5 * 1024 * 1024) * 10000 >= 5 * 1024**4


PART = 5 * 1024 * 1024


def _queued_entry(tmp_path, size):
    bag = tmp_path / "big.mcap"
    bag.write_bytes(b"x" * size)
    queue = UploadQueue(tmp_path / "q.db")
    entry = queue.add(bag, "r/big.mcap", backend="s3", destination={"bucket": "bags"})
    queue.mark_integrity(entry.id, "digest", size)
    return bag, queue, queue.get(entry.id)


def test_multipart_resume_skips_confirmed_parts(tmp_path, fake_s3_client):
    bag, queue, entry = _queued_entry(tmp_path, 2 * PART + 1)  # 3 parts
    original_upload_part = fake_s3_client.upload_part
    sent = []

    def crash_after_first_part(**kwargs):
        if sent:
            raise ConnectionError("network down")
        sent.append(kwargs["PartNumber"])
        return original_upload_part(**kwargs)

    fake_s3_client.upload_part = crash_after_first_part
    with pytest.raises(ConnectionError):
        backend(fake_s3_client).upload_entry(entry, queue, bag, PART)
    assert [p.part_number for p in queue.get_parts(entry.id)] == [1]

    # "Restart": a fresh backend resumes from the state persisted in the queue.
    fake_s3_client.upload_part = original_upload_part
    fake_s3_client.calls.clear()
    backend(fake_s3_client).upload_entry(entry, queue, bag, PART)

    resent = [c[1]["PartNumber"] for c in fake_s3_client.calls if c[0] == "upload_part"]
    assert resent == [2, 3]
    assert fake_s3_client.objects[("bags", "r/big.mcap")]["ContentLength"] == 2 * PART + 1
    assert queue.get_multipart(entry.id) is None


def test_expired_multipart_session_is_cleared(tmp_path, fake_s3_client):
    bag, queue, entry = _queued_entry(tmp_path, PART + 1)
    queue.create_multipart(entry.id, "gone", "bags", entry.remote_path, PART, PART + 1, "digest")
    with pytest.raises(InvalidSessionError):
        backend(fake_s3_client).upload_entry(entry, queue, bag, PART)
    assert queue.get_multipart(entry.id) is None


def test_existing_different_object_is_a_conflict(tmp_path, fake_s3_client):
    bag, queue, entry = _queued_entry(tmp_path, 10)
    fake_s3_client.objects[("bags", "r/big.mcap")] = {"ContentLength": 3, "Metadata": {}}
    with pytest.raises(ConflictBackendError):
        backend(fake_s3_client).upload_entry(entry, queue, bag, PART)
