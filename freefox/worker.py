"""Upload worker pool.

Each worker thread takes the next ready entry from the durable queue, computes its BLAKE3
fingerprint, hands it to the right storage backend and records the outcome in the queue.
Backend errors are mapped to a queue decision: done, deferred, retried, failed or conflict.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from freefox.backends import (
    AuthenticationBackendError,
    ConfigurationBackendError,
    ConflictBackendError,
    QuotaBackendError,
    TransientBackendError,
)
from freefox.integrity import calculate_blake3
from freefox.queue import QueueEntry, UploadQueue

if TYPE_CHECKING:
    from freefox.backends import StorageBackend
    from freefox.backends.factory import BackendRegistry
    from freefox.config import UploadConfig

logger = logging.getLogger(__name__)

# How long an idle worker waits before polling the queue again.
_IDLE_POLL_SECONDS = 2.0

# Substrings of provider error messages that indicate a temporary network problem.
_TRANSIENT_NETWORK_MARKERS = (
    "temporary failure in name resolution",
    "nameresolutionerror",
    "failed to resolve",
    "read timed out",
    "connect timed out",
    "connection timed out",
    "max retries exceeded",
    "connection reset",
    "connection aborted",
    "temporarily unavailable",
    "transient drive upload error",
)


def _is_storage_quota_error(error_msg: str) -> bool:
    message = error_msg.lower()
    return "storagequotaexceeded" in message or "storage quota" in message


def _is_transient_network_error(error_msg: str) -> bool:
    message = error_msg.lower()
    return any(marker in message for marker in _TRANSIENT_NETWORK_MARKERS)


class UploadWorkerPool:
    """A pool of threads that drain the upload queue.

    Pass either a ``registry`` (one backend per queued destination, used by the service) or a
    single ``backend`` (handy for scripts and tests).
    """

    def __init__(
        self,
        queue: UploadQueue,
        backend: StorageBackend | None = None,
        config: UploadConfig | None = None,
        delete_after: bool = False,
        registry: BackendRegistry | None = None,
    ) -> None:
        self._queue = queue
        self._backend = backend
        self._registry = registry
        self._config = config
        self._delete_after = delete_after
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        # One lock per remote destination, so two workers never write the same object.
        self._key_locks: dict[str, threading.Lock] = {}
        self._key_locks_guard = threading.Lock()

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        for index in range(self._config.workers):
            thread = threading.Thread(
                target=self._run, args=(index,), daemon=True, name=f"uploader-{index}"
            )
            thread.start()
            self._threads.append(thread)

    def stop(self, drain_timeout: float = 30.0) -> None:
        self._stop.set()
        deadline = time.monotonic() + drain_timeout
        for thread in self._threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        pending = self._queue.pending_count()
        if pending:
            logger.warning("%d items still pending in queue", pending)

    # ------------------------------------------------------------------ main loop

    def _run(self, worker_id: int) -> None:
        while not self._stop.is_set():
            entry = self._queue.next_ready()
            if entry is None:
                self._stop.wait(_IDLE_POLL_SECONDS)
                continue
            self._process(entry)

    def _process(self, entry: QueueEntry) -> None:
        """Upload one entry and record the outcome. Never raises."""
        local = Path(entry.local_path)
        if not local.exists():
            self._queue.mark_failed(entry.id, "local file missing", max_retries=0)
            return
        try:
            self._ensure_fingerprint(entry, local)
            backend = self._backend_for(entry)
            with self._lock_for(self._destination_key(entry)):
                uploaded = self._upload(backend, entry, local)
                self._queue.mark_done(entry.id)
                if uploaded and self._delete_after:
                    local.unlink()
        except Exception as exc:
            self._handle_error(entry, local, exc)

    def _upload(self, backend: StorageBackend, entry: QueueEntry, local: Path) -> bool:
        """Send *entry* to *backend*.

        Returns False when nothing was sent because the remote already holds this content.
        """

        def on_progress(percent: float, uploaded_bytes: int) -> None:
            self._record_progress(entry.id, percent, uploaded_bytes)

        # Backends with their own resume state (S3 multipart) take full control.
        upload_entry = getattr(backend, "upload_entry", None)
        if callable(upload_entry):
            upload_entry(entry, self._queue, local, self._config.chunk_size, on_progress)
            return True

        digest = entry.blake3_digest
        if (
            digest
            and self._config.deduplicate_by_hash
            and backend.find_duplicate(entry.remote_path, digest, entry.size_bytes)
        ):
            return False
        if not digest and backend.exists(entry.remote_path):
            return False

        def on_session(session_uri: str) -> None:
            self._queue.mark_upload_session(entry.id, session_uri)

        backend.upload(
            local,
            entry.remote_path,
            chunk_size=self._config.chunk_size,
            progress_callback=on_progress,
            session_uri=entry.upload_session_uri,
            session_callback=on_session,
            blake3_digest=digest,
            expected_size=entry.size_bytes,
        )
        return True

    # ------------------------------------------------------------------ error policy

    def _handle_error(self, entry: QueueEntry, local: Path, exc: Exception) -> None:
        config = self._config
        if isinstance(exc, ConflictBackendError):
            logger.error(
                "bag=%s backend=%s destination=%s disposition=operator conflict=%s",
                local.name,
                entry.backend,
                entry.remote_path,
                exc,
            )
            self._queue.mark_conflict(entry.id, str(exc))
        elif isinstance(exc, QuotaBackendError):
            self._queue.defer(entry.id, str(exc), config.quota_retry_delay)
        elif isinstance(exc, TransientBackendError):
            self._queue.defer(entry.id, str(exc), config.transient_retry_delay)
        elif isinstance(exc, (AuthenticationBackendError, ConfigurationBackendError)):
            # Retrying will not help until an operator fixes credentials or configuration.
            logger.error(
                "bag=%s backend=%s destination=%s disposition=failed cause=%s",
                local.name,
                entry.backend,
                entry.remote_path,
                exc,
            )
            self._queue.mark_failed(entry.id, str(exc), max_retries=0)
        elif _is_storage_quota_error(str(exc)):
            self._queue.defer(entry.id, "Storage quota exceeded", config.quota_retry_delay)
        elif _is_transient_network_error(str(exc)):
            self._queue.defer(entry.id, "Temporary network error", config.transient_retry_delay)
        else:
            logger.warning("bag=%s upload error: %s", local.name, exc)
            self._queue.mark_failed(
                entry.id,
                str(exc),
                backoff_base=config.retry_backoff_base,
                backoff_max=config.retry_backoff_max,
                max_retries=config.max_retries,
            )

    # ------------------------------------------------------------------ helpers

    def _ensure_fingerprint(self, entry: QueueEntry, local: Path) -> None:
        """Compute and persist the BLAKE3 digest once per entry, if enabled."""
        if not self._config.verify_blake3 or entry.blake3_digest:
            return
        digest = calculate_blake3(local, chunk_size=max(1024 * 1024, self._config.chunk_size))
        size = local.stat().st_size
        self._queue.mark_integrity(entry.id, digest, size)
        entry.blake3_digest = digest
        entry.size_bytes = size

    def _backend_for(self, entry: QueueEntry) -> StorageBackend:
        if self._registry is not None:
            return self._registry.get(entry.backend, entry.destination)
        return self._backend

    @staticmethod
    def _destination_key(entry: QueueEntry) -> str:
        return f"{entry.backend}:{entry.destination_json}:{entry.remote_path}"

    def _lock_for(self, key: str) -> threading.Lock:
        with self._key_locks_guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def _record_progress(self, entry_id: int, percent: float, uploaded_bytes: int) -> None:
        try:
            self._queue.mark_progress(entry_id, percent, uploaded_bytes)
        except Exception as exc:
            logger.warning("Could not record upload progress for #%d: %s", entry_id, exc)
