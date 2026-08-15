"""Upload worker pool — pulls entries from the queue and uploads them."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from freefox.integrity import calculate_blake3
from freefox.queue import UploadQueue

if TYPE_CHECKING:
    from freefox.backends import StorageBackend
    from freefox.config import UploadConfig

logger = logging.getLogger(__name__)


def _is_storage_quota_error(error_msg: str) -> bool:
    lowered = error_msg.lower()
    return (
        "storagequotaexceeded" in lowered
        or "drive storage quota has been exceeded" in lowered
        or "storage quota" in lowered
    )


def _is_transient_network_error(error_msg: str) -> bool:
    lowered = error_msg.lower()
    return any(
        marker in lowered
        for marker in (
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
    )


class UploadWorkerPool:
    """Fixed pool of threads that drain the upload queue."""

    def __init__(
        self,
        queue: UploadQueue,
        backend: "StorageBackend",
        config: "UploadConfig",
        delete_after: bool = False,
    ) -> None:
        self._queue = queue
        self._backend = backend
        self._config = config
        self._delete_after = delete_after
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_progress(
        self,
        entry_id: int,
        progress_percent: float,
        uploaded_bytes: int,
    ) -> None:
        try:
            self._queue.mark_progress(entry_id, progress_percent, uploaded_bytes)
        except Exception as exc:
            logger.warning("Could not record upload progress for #%d: %s", entry_id, exc)

    def _record_session(self, entry_id: int, session_uri: str) -> None:
        try:
            self._queue.mark_upload_session(entry_id, session_uri)
        except Exception as exc:
            logger.warning("Could not record upload session for #%d: %s", entry_id, exc)

    def _worker(self, worker_id: int) -> None:
        logger.debug("Upload worker %d started", worker_id)
        while not self._stop.is_set():
            entry = self._queue.next_ready()
            if entry is None:
                self._stop.wait(2.0)
                continue

            local = Path(entry.local_path)
            if not local.exists():
                logger.error(
                    "File not found (already moved?): %s — marking failed", local
                )
                self._queue.mark_failed(
                    entry.id,
                    "local file missing",
                    max_retries=0,
                )
                continue

            blake3_digest = entry.blake3_digest
            if self._config.verify_blake3 and not blake3_digest:
                logger.info(
                    "[worker %d] calcul BLAKE3 de %s",
                    worker_id,
                    local.name,
                )
                blake3_digest = calculate_blake3(
                    local,
                    chunk_size=max(1024 * 1024, self._config.chunk_size),
                )
                self._queue.mark_integrity(
                    entry.id,
                    blake3_digest,
                    local.stat().st_size,
                )
                entry.blake3_digest = blake3_digest
                entry.size_bytes = local.stat().st_size

            # Dedup: with BLAKE3 enabled, skip only when content matches.
            try:
                find_duplicate = getattr(self._backend, "find_duplicate", None)
                if (
                    self._config.verify_blake3
                    and self._config.deduplicate_by_hash
                    and blake3_digest
                    and callable(find_duplicate)
                    and find_duplicate(
                        entry.remote_path,
                        blake3_digest,
                        entry.size_bytes,
                    )
                ):
                    logger.info(
                        "Doublon distant detecte par BLAKE3, skip: %s",
                        entry.remote_path,
                    )
                    self._queue.mark_done(entry.id)
                    continue

                if not blake3_digest and self._backend.exists(entry.remote_path):
                    logger.info(
                        "Remote already exists, skipping: %s", entry.remote_path
                    )
                    self._queue.mark_done(entry.id)
                    continue
            except Exception as exc:
                logger.warning("exists() check failed (%s) — proceeding", exc)

            try:
                self._backend.upload(
                    local,
                    entry.remote_path,
                    chunk_size=self._config.chunk_size,
                    progress_callback=lambda pct, uploaded, entry_id=entry.id: (
                        self._record_progress(entry_id, pct, uploaded)
                    ),
                    session_uri=entry.upload_session_uri,
                    session_callback=lambda uri, entry_id=entry.id: (
                        self._record_session(entry_id, uri)
                    ),
                    blake3_digest=blake3_digest,
                    expected_size=entry.size_bytes,
                )
                self._queue.mark_done(entry.id)
                logger.info("[worker %d] done: %s", worker_id, local.name)

                if self._delete_after:
                    try:
                        local.unlink()
                        logger.info("Deleted local: %s", local)
                    except OSError as exc:
                        logger.warning("Could not delete %s: %s", local, exc)

            except Exception as exc:
                error_msg = str(exc)
                if _is_storage_quota_error(error_msg):
                    retry_delay = self._config.quota_retry_delay
                    logger.warning(
                        "[worker %d] quota Google Drive depasse pour %s; "
                        "nouvel essai dans %.0f min",
                        worker_id,
                        local.name,
                        retry_delay / 60,
                    )
                    self._queue.defer(
                        entry.id,
                        "Quota Google Drive depasse. FreeFox reessaiera automatiquement.",
                        retry_after_seconds=retry_delay,
                    )
                    continue

                if _is_transient_network_error(error_msg):
                    retry_delay = self._config.transient_retry_delay
                    logger.warning(
                        "[worker %d] erreur reseau temporaire pour %s; "
                        "nouvel essai dans %.0f s",
                        worker_id,
                        local.name,
                        retry_delay,
                    )
                    self._queue.defer(
                        entry.id,
                        "Erreur reseau temporaire. FreeFox reessaiera automatiquement.",
                        retry_after_seconds=retry_delay,
                    )
                    continue

                logger.warning(
                    "[worker %d] upload failed (%s): %s — retry %d/%d",
                    worker_id,
                    local.name,
                    error_msg,
                    entry.retries + 1,
                    self._config.max_retries,
                )
                self._queue.mark_failed(
                    entry.id,
                    error_msg,
                    backoff_base=self._config.retry_backoff_base,
                    backoff_max=self._config.retry_backoff_max,
                    max_retries=self._config.max_retries,
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        for i in range(self._config.workers):
            t = threading.Thread(
                target=self._worker,
                args=(i,),
                daemon=True,
                name=f"uploader-{i}",
            )
            t.start()
            self._threads.append(t)
        logger.info("Upload pool started (%d workers)", self._config.workers)

    def stop(self, drain_timeout: float = 30.0) -> None:
        """Signal workers to stop. Waits up to *drain_timeout* for current uploads."""
        self._stop.set()
        deadline = time.monotonic() + drain_timeout
        for t in self._threads:
            remaining = max(0.0, deadline - time.monotonic())
            t.join(timeout=remaining)
        pending = self._queue.pending_count()
        if pending:
            logger.warning("%d items still pending in queue", pending)
