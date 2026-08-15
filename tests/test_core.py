"""Unit tests — no network, no Google Drive, fully offline."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from freefox.queue import UploadQueue, Status
from freefox.watcher import StabilityTracker
from freefox.integrity import calculate_blake3
from freefox.config import CollectorConfig
from freefox.backends.rsync import _parse_progress_percent


# ──────────────────────────────────────────────────────────────────────
# Queue tests
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def queue(tmp_path):
    return UploadQueue(tmp_path / "test.db")


def test_add_and_retrieve(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x" * 100)
    entry = queue.add(f, "robot-01/2024-01-01/bag.mcap")
    assert entry is not None
    assert entry.status == Status.QUEUED
    assert entry.size_bytes == 100


def test_add_duplicate_returns_none(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    queue.add(f, "remote/bag.mcap")
    second = queue.add(f, "remote/bag.mcap")
    assert second is None


def test_next_ready_claims_entry(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    queue.add(f, "remote/bag.mcap")
    entry = queue.next_ready()
    assert entry is not None
    assert entry.status == Status.UPLOADING
    # Should not be returned again
    assert queue.next_ready() is None


def test_mark_done(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    queue.add(f, "remote/bag.mcap")
    entry = queue.next_ready()
    queue.mark_done(entry.id)
    refreshed = queue.get(entry.id)
    assert refreshed.status == Status.DONE


def test_calculate_blake3_is_stable(tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"freefox")
    assert calculate_blake3(f) == calculate_blake3(f)


def test_mark_integrity(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x" * 12)
    entry = queue.add(f, "remote/bag.mcap")
    queue.mark_integrity(entry.id, "abc123", 12)

    refreshed = queue.get(entry.id)
    assert refreshed.blake3_digest == "abc123"
    assert refreshed.size_bytes == 12


def test_config_accepts_rsync_backend(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
robot_id: robot-test
watch:
  directory: /tmp/bags
storage:
  backend: rsync
rsync:
  destination: /tmp/freefox-rsync
"""
    )

    config = CollectorConfig.from_yaml(config_file)
    assert config.storage.backend == "rsync"
    assert config.rsync.destination == "/tmp/freefox-rsync"


def test_rsync_progress_parser():
    assert _parse_progress_percent("  12,345,678  42%   11.8MB/s") == 42.0
    assert _parse_progress_percent("no progress here") is None


def test_retry_increments(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    queue.add(f, "remote/bag.mcap")
    entry = queue.next_ready()
    queue.mark_failed(entry.id, "timeout", backoff_base=0.01, backoff_max=1.0, max_retries=3)
    refreshed = queue.get(entry.id)
    assert refreshed.retries == 1
    assert refreshed.status == Status.QUEUED
    breakdown = queue.queued_breakdown()
    assert breakdown["ready"] == 0
    assert breakdown["waiting"] == 1


def test_defer_keeps_retry_count(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    queue.add(f, "remote/bag.mcap")
    entry = queue.next_ready()
    queue.defer(entry.id, "Erreur reseau temporaire", retry_after_seconds=30)

    refreshed = queue.get(entry.id)
    assert refreshed.status == Status.QUEUED
    assert refreshed.retries == 0
    assert queue.next_ready() is None


def test_max_retries_marks_failed(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    queue.add(f, "remote/bag.mcap")
    for _ in range(3):
        entry = queue.next_ready()
        if entry is None:
            # not yet past retry window in fast test — force it
            import sqlite3
            conn = sqlite3.connect(str(queue._path))
            conn.execute("UPDATE queue SET next_retry_at=0 WHERE status='queued'")
            conn.commit()
            conn.close()
            entry = queue.next_ready()
        queue.mark_failed(entry.id, "err", backoff_base=0.0, backoff_max=0.0, max_retries=3)

    final = queue.get(entry.id)
    assert final.status == Status.FAILED


def test_requeue_failed_resets_entry(queue, tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    queue.add(f, "remote/bag.mcap")
    entry = queue.next_ready()
    queue.mark_failed(entry.id, "err", max_retries=0)

    assert queue.get(entry.id).status == Status.FAILED
    assert queue.requeue_failed() == 1

    retried = queue.next_ready()
    assert retried is not None
    assert retried.id == entry.id
    assert retried.status == Status.UPLOADING
    assert retried.retries == 0
    assert retried.error is None


def test_stats(queue, tmp_path):
    for i in range(3):
        f = tmp_path / f"bag{i}.mcap"
        f.write_bytes(b"x")
        queue.add(f, f"remote/bag{i}.mcap")
    stats = queue.stats()
    assert stats.get("queued", 0) == 3


def test_restart_resets_uploading(tmp_path):
    """Entries stuck as UPLOADING on restart are reset to QUEUED."""
    db = tmp_path / "q.db"
    q1 = UploadQueue(db)
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x")
    q1.add(f, "r")
    q1.next_ready()  # now UPLOADING

    # Simulate restart
    q2 = UploadQueue(db)
    entry = q2.next_ready()
    assert entry is not None  # was reset to QUEUED


# ──────────────────────────────────────────────────────────────────────
# StabilityTracker tests
# ──────────────────────────────────────────────────────────────────────


def test_stable_after_wait(tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x" * 1000)
    tracker = StabilityTracker(stable_seconds=0.1)
    # First call — starts the clock
    assert tracker.update(f) is False
    time.sleep(0.15)
    # Second call — stable window elapsed
    assert tracker.update(f) is True


def test_not_stable_if_growing(tmp_path):
    f = tmp_path / "bag.mcap"
    f.write_bytes(b"x" * 100)
    tracker = StabilityTracker(stable_seconds=0.05)
    tracker.update(f)
    f.write_bytes(b"x" * 200)
    time.sleep(0.08)
    tracker.update(f)  # size changed — resets clock
    assert tracker.update(f) is False


def test_missing_file(tmp_path):
    f = tmp_path / "ghost.mcap"
    tracker = StabilityTracker(stable_seconds=0.0)
    assert tracker.update(f) is False
