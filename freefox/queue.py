"""Persistent upload queue backed by SQLite.

States
------
pending   → file detected, waiting for stable check
queued    → stable, ready to upload
uploading → worker has claimed this entry
done      → upload confirmed
failed    → max retries exceeded
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Status(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    UPLOADING = "uploading"
    DONE = "done"
    FAILED = "failed"


@dataclass
class QueueEntry:
    id: int
    local_path: str
    remote_path: str
    status: Status
    retries: int
    next_retry_at: float  # unix timestamp
    created_at: float
    size_bytes: int
    progress_percent: float = 0.0
    uploaded_bytes: int = 0
    updated_at: float = 0.0
    upload_started_at: float = 0.0
    upload_finished_at: float = 0.0
    upload_session_uri: str = ""
    blake3_digest: str = ""
    error: Optional[str] = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    local_path   TEXT    NOT NULL UNIQUE,
    remote_path  TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'queued',
    retries      INTEGER NOT NULL DEFAULT 0,
    next_retry_at REAL   NOT NULL DEFAULT 0,
    created_at   REAL    NOT NULL,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    progress_percent REAL NOT NULL DEFAULT 0,
    uploaded_bytes INTEGER NOT NULL DEFAULT 0,
    updated_at   REAL    NOT NULL DEFAULT 0,
    upload_started_at REAL NOT NULL DEFAULT 0,
    upload_finished_at REAL NOT NULL DEFAULT 0,
    upload_session_uri TEXT NOT NULL DEFAULT '',
    blake3_digest TEXT NOT NULL DEFAULT '',
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_status ON queue(status, next_retry_at);
"""


class UploadQueue:
    """Thread-safe, persistent upload queue."""

    def __init__(self, db_path: Path, initialize: bool = True) -> None:
        self._path = db_path
        self._initialize = initialize
        self._local = threading.local()
        self._lock = threading.Lock()
        if initialize:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        """One connection per thread (SQLite WAL mode)."""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                str(self._path),
                timeout=60,
                isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=60000")
            if self._initialize:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.executescript(_SCHEMA)
        self._migrate(conn)
        conn.commit()
        # Reset any interrupted uploads so they are re-tried on restart
        conn.execute(
            "UPDATE queue SET status=? WHERE status=?",
            (Status.QUEUED, Status.UPLOADING),
        )
        conn.commit()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(queue)").fetchall()
        }
        if "progress_percent" not in columns:
            conn.execute(
                "ALTER TABLE queue ADD COLUMN progress_percent REAL NOT NULL DEFAULT 0"
            )
        if "updated_at" not in columns:
            conn.execute(
                "ALTER TABLE queue ADD COLUMN updated_at REAL NOT NULL DEFAULT 0"
            )
        if "uploaded_bytes" not in columns:
            conn.execute(
                "ALTER TABLE queue ADD COLUMN uploaded_bytes INTEGER NOT NULL DEFAULT 0"
            )
        if "upload_started_at" not in columns:
            conn.execute(
                "ALTER TABLE queue ADD COLUMN upload_started_at REAL NOT NULL DEFAULT 0"
            )
        if "upload_finished_at" not in columns:
            conn.execute(
                "ALTER TABLE queue ADD COLUMN upload_finished_at REAL NOT NULL DEFAULT 0"
            )
        if "upload_session_uri" not in columns:
            conn.execute(
                "ALTER TABLE queue ADD COLUMN upload_session_uri TEXT NOT NULL DEFAULT ''"
            )
        if "blake3_digest" not in columns:
            conn.execute(
                "ALTER TABLE queue ADD COLUMN blake3_digest TEXT NOT NULL DEFAULT ''"
            )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> QueueEntry:
        def value(name: str, default):
            try:
                return row[name]
            except IndexError:
                return default

        return QueueEntry(
            id=row["id"],
            local_path=row["local_path"],
            remote_path=row["remote_path"],
            status=Status(row["status"]),
            retries=row["retries"],
            next_retry_at=row["next_retry_at"],
            created_at=row["created_at"],
            size_bytes=row["size_bytes"],
            progress_percent=row["progress_percent"],
            uploaded_bytes=row["uploaded_bytes"],
            updated_at=row["updated_at"],
            upload_started_at=row["upload_started_at"],
            upload_finished_at=row["upload_finished_at"],
            upload_session_uri=row["upload_session_uri"],
            blake3_digest=value("blake3_digest", ""),
            error=row["error"],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, local_path: Path, remote_path: str) -> Optional[QueueEntry]:
        """Enqueue a file. Returns None if already in queue."""
        conn = self._conn()
        size = local_path.stat().st_size if local_path.exists() else 0
        try:
            with self._lock:
                cur = conn.execute(
                    """
                    INSERT INTO queue (
                        local_path,
                        remote_path,
                        status,
                        created_at,
                        updated_at,
                        upload_started_at,
                        upload_finished_at,
                        size_bytes,
                        progress_percent,
                        uploaded_bytes,
                        upload_session_uri
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(local_path),
                        remote_path,
                        Status.QUEUED,
                        time.time(),
                        time.time(),
                        0.0,
                        0.0,
                        size,
                        0.0,
                        0,
                        "",
                    ),
                )
                conn.commit()
                return self.get(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None  # already queued

    def get(self, entry_id: int) -> Optional[QueueEntry]:
        row = self._conn().execute(
            "SELECT * FROM queue WHERE id=?", (entry_id,)
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def next_ready(self) -> Optional[QueueEntry]:
        """Claim the next entry ready for upload (status=queued, retry window elapsed)."""
        now = time.time()
        with self._lock:
            conn = self._conn()
            row = conn.execute(
                """
                SELECT * FROM queue
                WHERE status=? AND next_retry_at <= ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (Status.QUEUED, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """
                UPDATE queue
                SET status=?,
                    progress_percent=?,
                    uploaded_bytes=?,
                    updated_at=?,
                    upload_started_at=?,
                    upload_finished_at=?
                WHERE id=?
                """,
                (
                    Status.UPLOADING,
                    row["progress_percent"],
                    row["uploaded_bytes"],
                    time.time(),
                    row["upload_started_at"] or time.time(),
                    0.0,
                    row["id"],
                ),
            )
            conn.commit()
        entry = self._row_to_entry(row)
        entry.status = Status.UPLOADING
        return entry

    def mark_done(self, entry_id: int) -> None:
        conn = self._conn()
        with self._lock:
            conn.execute(
                """
                UPDATE queue
                SET status=?,
                    progress_percent=?,
                    uploaded_bytes=size_bytes,
                    updated_at=?,
                    upload_finished_at=?,
                    error=NULL
                WHERE id=?
                """,
                (Status.DONE, 100.0, time.time(), time.time(), entry_id),
            )
            conn.commit()

    def mark_progress(
        self,
        entry_id: int,
        progress_percent: float,
        uploaded_bytes: int | None = None,
    ) -> None:
        progress_percent = max(0.0, min(100.0, progress_percent))
        conn = self._conn()
        with self._lock:
            if uploaded_bytes is None:
                conn.execute(
                    """
                    UPDATE queue
                    SET progress_percent=?, updated_at=?
                    WHERE id=? AND status=?
                    """,
                    (progress_percent, time.time(), entry_id, Status.UPLOADING),
                )
            else:
                conn.execute(
                    """
                    UPDATE queue
                    SET progress_percent=?, uploaded_bytes=?, updated_at=?
                    WHERE id=? AND status=?
                    """,
                    (
                        progress_percent,
                        max(0, uploaded_bytes),
                        time.time(),
                        entry_id,
                        Status.UPLOADING,
                    ),
                )
            conn.commit()

    def mark_upload_session(self, entry_id: int, session_uri: str) -> None:
        conn = self._conn()
        with self._lock:
            conn.execute(
                """
                UPDATE queue
                SET upload_session_uri=?, updated_at=?
                WHERE id=?
                """,
                (session_uri, time.time(), entry_id),
            )
            conn.commit()

    def mark_integrity(
        self,
        entry_id: int,
        blake3_digest: str,
        size_bytes: int,
    ) -> None:
        conn = self._conn()
        with self._lock:
            conn.execute(
                """
                UPDATE queue
                SET blake3_digest=?,
                    size_bytes=?,
                    updated_at=?
                WHERE id=?
                """,
                (blake3_digest, max(0, size_bytes), time.time(), entry_id),
            )
            conn.commit()

    def clear_upload_session(self, entry_id: int) -> None:
        conn = self._conn()
        with self._lock:
            conn.execute(
                """
                UPDATE queue
                SET upload_session_uri='',
                    uploaded_bytes=0,
                    progress_percent=0,
                    updated_at=?
                WHERE id=?
                """,
                (time.time(), entry_id),
            )
            conn.commit()

    def mark_failed(
        self,
        entry_id: int,
        error: str,
        backoff_base: float = 2.0,
        backoff_max: float = 300.0,
        max_retries: int = 10,
    ) -> None:
        conn = self._conn()
        with self._lock:
            row = conn.execute(
                "SELECT retries FROM queue WHERE id=?", (entry_id,)
            ).fetchone()
            if not row:
                return
            retries = row["retries"] + 1
            if retries >= max_retries:
                conn.execute(
                    """
                    UPDATE queue
                    SET status=?,
                        retries=?,
                        updated_at=?,
                        upload_finished_at=?,
                        error=?
                    WHERE id=?
                    """,
                    (Status.FAILED, retries, time.time(), time.time(), error, entry_id),
                )
            else:
                delay = min(backoff_base**retries, backoff_max)
                next_retry = time.time() + delay
                conn.execute(
                    """
                    UPDATE queue
                    SET status=?, retries=?, next_retry_at=?, error=?
                    , updated_at=?
                    WHERE id=?
                    """,
                    (Status.QUEUED, retries, next_retry, error, time.time(), entry_id),
                )
            conn.commit()

    def defer(
        self,
        entry_id: int,
        error: str,
        retry_after_seconds: float,
    ) -> None:
        """Keep an entry queued, but postpone its next retry without failing it."""
        conn = self._conn()
        with self._lock:
            conn.execute(
                """
                UPDATE queue
                SET status=?,
                    next_retry_at=?,
                    updated_at=?,
                    upload_finished_at=0,
                    error=?
                WHERE id=?
                """,
                (
                    Status.QUEUED,
                    time.time() + max(0.0, retry_after_seconds),
                    time.time(),
                    error,
                    entry_id,
                ),
            )
            conn.commit()

    def requeue_failed(self, reset_retries: bool = True) -> int:
        """Move failed entries back to the front of the upload queue."""
        conn = self._conn()
        with self._lock:
            cur = conn.execute(
                """
                UPDATE queue
                SET status=?,
                    retries=CASE WHEN ? THEN 0 ELSE retries END,
                    next_retry_at=0,
                    progress_percent=0,
                    uploaded_bytes=0,
                    updated_at=?,
                    upload_started_at=0,
                    upload_finished_at=0,
                    upload_session_uri='',
                    error=NULL
                WHERE status=?
                """,
                (Status.QUEUED, reset_retries, time.time(), Status.FAILED),
            )
            conn.commit()
            return cur.rowcount

    def stats(self) -> dict[str, int]:
        rows = self._conn().execute(
            "SELECT status, COUNT(*) AS n FROM queue GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def queued_breakdown(self) -> dict[str, int]:
        """Return how many queued entries are ready now vs waiting for retry."""
        now = time.time()
        row = self._conn().execute(
            """
            SELECT
                SUM(CASE WHEN next_retry_at <= ? THEN 1 ELSE 0 END) AS ready,
                SUM(CASE WHEN next_retry_at > ? THEN 1 ELSE 0 END) AS waiting
            FROM queue
            WHERE status=?
            """,
            (now, now, Status.QUEUED),
        ).fetchone()
        return {
            "ready": int(row["ready"] or 0),
            "waiting": int(row["waiting"] or 0),
        }

    def pending_count(self) -> int:
        row = self._conn().execute(
            "SELECT COUNT(*) FROM queue WHERE status IN (?,?)",
            (Status.QUEUED, Status.UPLOADING),
        ).fetchone()
        return row[0]

    def recent(self, limit: int = 10) -> list[QueueEntry]:
        rows = self._conn().execute(
            "SELECT * FROM queue ORDER BY updated_at DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]
