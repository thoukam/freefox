"""Thread-safe durable SQLite upload queue."""
from __future__ import annotations

import json
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
    CONFLICT = "conflict"


@dataclass
class QueueEntry:
    id: int
    local_path: str
    remote_path: str
    status: Status
    retries: int
    next_retry_at: float
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
    backend: str = "gdrive"
    destination_json: str = "{}"

    @property
    def destination(self) -> dict:
        try:
            value = json.loads(self.destination_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


@dataclass(frozen=True)
class MultipartUpload:
    queue_id: int
    upload_id: str
    bucket: str
    object_key: str
    part_size: int
    source_size: int
    source_blake3: str
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class MultipartPart:
    queue_id: int
    part_number: int
    etag: str
    size_bytes: int
    updated_at: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
 id INTEGER PRIMARY KEY AUTOINCREMENT, local_path TEXT NOT NULL UNIQUE,
 remote_path TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', retries INTEGER NOT NULL DEFAULT 0,
 next_retry_at REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0,
 progress_percent REAL NOT NULL DEFAULT 0, uploaded_bytes INTEGER NOT NULL DEFAULT 0,
 updated_at REAL NOT NULL DEFAULT 0, upload_started_at REAL NOT NULL DEFAULT 0,
 upload_finished_at REAL NOT NULL DEFAULT 0, upload_session_uri TEXT NOT NULL DEFAULT '',
 blake3_digest TEXT NOT NULL DEFAULT '', error TEXT, backend TEXT, destination_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_status ON queue(status, next_retry_at);
CREATE TABLE IF NOT EXISTS s3_multipart_uploads (
 queue_id INTEGER PRIMARY KEY REFERENCES queue(id) ON DELETE CASCADE,
 upload_id TEXT NOT NULL, bucket TEXT NOT NULL, object_key TEXT NOT NULL,
 part_size INTEGER NOT NULL, source_size INTEGER NOT NULL, source_blake3 TEXT NOT NULL DEFAULT '',
 created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS s3_multipart_parts (
 queue_id INTEGER NOT NULL REFERENCES s3_multipart_uploads(queue_id) ON DELETE CASCADE,
 part_number INTEGER NOT NULL CHECK(part_number BETWEEN 1 AND 10000), etag TEXT NOT NULL,
 size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0), updated_at REAL NOT NULL,
 PRIMARY KEY(queue_id, part_number)
);
"""


class UploadQueue:
    def __init__(self, db_path: Path, initialize: bool = True, legacy_backend: str | None = None, legacy_destination: dict | None = None) -> None:
        self._path = db_path
        self._initialize = initialize
        self._legacy_backend = legacy_backend
        self._legacy_destination = legacy_destination or {}
        self._local = threading.local()
        self._lock = threading.RLock()
        if initialize:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(str(self._path), timeout=60, isolation_level=None)
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
        existing = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='queue'").fetchone()
        if existing:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(queue)")}
            if "backend" not in columns or "destination_json" not in columns:
                rows = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
                if rows and self._legacy_backend not in {"gdrive", "rsync"}:
                    raise RuntimeError("Legacy queue backend is ambiguous; set storage.legacy_backend to gdrive or rsync")
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.executescript(_SCHEMA)
                self._migrate(conn)
                conn.execute("UPDATE queue SET status=? WHERE status=?", (Status.QUEUED, Status.UPLOADING))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(queue)")}
        additions = {
            "progress_percent": "REAL NOT NULL DEFAULT 0", "updated_at": "REAL NOT NULL DEFAULT 0",
            "uploaded_bytes": "INTEGER NOT NULL DEFAULT 0", "upload_started_at": "REAL NOT NULL DEFAULT 0",
            "upload_finished_at": "REAL NOT NULL DEFAULT 0", "upload_session_uri": "TEXT NOT NULL DEFAULT ''",
            "blake3_digest": "TEXT NOT NULL DEFAULT ''", "backend": "TEXT", "destination_json": "TEXT",
        }
        for name, ddl in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE queue ADD COLUMN {name} {ddl}")
        count = conn.execute("SELECT COUNT(*) FROM queue WHERE backend IS NULL OR destination_json IS NULL").fetchone()[0]
        if count:
            if self._legacy_backend not in {"gdrive", "rsync"}:
                raise RuntimeError("Legacy queue backend is ambiguous; set storage.legacy_backend to gdrive or rsync")
            snapshot = json.dumps(self._legacy_destination, sort_keys=True, separators=(",", ":"))
            conn.execute("UPDATE queue SET backend=?, destination_json=? WHERE backend IS NULL OR destination_json IS NULL", (self._legacy_backend, snapshot))

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> QueueEntry:
        keys=set(row.keys())
        value=lambda name, default: row[name] if name in keys and row[name] is not None else default
        return QueueEntry(id=row["id"], local_path=row["local_path"], remote_path=row["remote_path"],
            status=Status(row["status"]), retries=row["retries"], next_retry_at=row["next_retry_at"],
            created_at=row["created_at"], size_bytes=row["size_bytes"], progress_percent=value("progress_percent",0.0),
            uploaded_bytes=value("uploaded_bytes",0), updated_at=value("updated_at",0.0),
            upload_started_at=value("upload_started_at",0.0), upload_finished_at=value("upload_finished_at",0.0),
            upload_session_uri=value("upload_session_uri",""), blake3_digest=value("blake3_digest",""),
            error=value("error",None), backend=value("backend","gdrive"), destination_json=value("destination_json","{}"))

    def add(self, local_path: Path, remote_path: str, backend: str = "gdrive", destination: dict | None = None) -> Optional[QueueEntry]:
        if backend not in {"gdrive", "rsync", "s3"}: raise ValueError(f"Unsupported backend: {backend}")
        snapshot=json.dumps(destination or {}, sort_keys=True, separators=(",", ":"))
        now=time.time(); size=local_path.stat().st_size if local_path.exists() else 0
        try:
            with self._lock:
                cur=self._conn().execute("INSERT INTO queue(local_path,remote_path,status,created_at,updated_at,size_bytes,backend,destination_json) VALUES(?,?,?,?,?,?,?,?)", (str(local_path),remote_path,Status.QUEUED,now,now,size,backend,snapshot))
                self._conn().commit(); return self.get(cur.lastrowid)
        except sqlite3.IntegrityError: return None

    def get(self, entry_id: int) -> Optional[QueueEntry]:
        row=self._conn().execute("SELECT * FROM queue WHERE id=?",(entry_id,)).fetchone(); return self._row_to_entry(row) if row else None

    def next_ready(self) -> Optional[QueueEntry]:
        with self._lock:
            conn=self._conn(); now=time.time(); conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("SELECT * FROM queue WHERE status=? AND next_retry_at<=? ORDER BY created_at LIMIT 1",(Status.QUEUED,now)).fetchone()
            if not row: conn.commit(); return None
            conn.execute("UPDATE queue SET status=?,updated_at=?,upload_started_at=CASE WHEN upload_started_at=0 THEN ? ELSE upload_started_at END,upload_finished_at=0 WHERE id=?",(Status.UPLOADING,now,now,row["id"])); conn.commit()
            entry=self.get(row["id"]); assert entry; return entry

    def mark_done(self, entry_id: int) -> None:
        now=time.time(); self._conn().execute("UPDATE queue SET status=?,progress_percent=100,uploaded_bytes=size_bytes,updated_at=?,upload_finished_at=?,error=NULL WHERE id=?",(Status.DONE,now,now,entry_id)); self._conn().commit()

    def mark_conflict(self, entry_id: int, error: str) -> None:
        now=time.time(); self._conn().execute("UPDATE queue SET status=?,updated_at=?,upload_finished_at=?,error=? WHERE id=?",(Status.CONFLICT,now,now,error,entry_id)); self._conn().commit()

    def mark_progress(self, entry_id: int, progress_percent: float, uploaded_bytes: int | None = None) -> None:
        pct=max(0.0,min(100.0,progress_percent)); uploaded=max(0,uploaded_bytes or 0)
        self._conn().execute("UPDATE queue SET progress_percent=?,uploaded_bytes=CASE WHEN ? IS NULL THEN uploaded_bytes ELSE ? END,updated_at=? WHERE id=? AND status=?",(pct,uploaded_bytes,uploaded,time.time(),entry_id,Status.UPLOADING)); self._conn().commit()

    def mark_upload_session(self, entry_id: int, session_uri: str) -> None:
        self._conn().execute("UPDATE queue SET upload_session_uri=?,updated_at=? WHERE id=?",(session_uri,time.time(),entry_id)); self._conn().commit()

    def mark_integrity(self, entry_id: int, blake3_digest: str, size_bytes: int) -> None:
        self._conn().execute("UPDATE queue SET blake3_digest=?,size_bytes=?,updated_at=? WHERE id=?",(blake3_digest,max(0,size_bytes),time.time(),entry_id)); self._conn().commit()

    def clear_upload_session(self, entry_id: int) -> None:
        self._conn().execute("UPDATE queue SET upload_session_uri='',uploaded_bytes=0,progress_percent=0,updated_at=? WHERE id=?",(time.time(),entry_id)); self._conn().commit()

    def mark_failed(self, entry_id: int, error: str, backoff_base: float=2.0, backoff_max: float=300.0, max_retries: int=10) -> None:
        row=self._conn().execute("SELECT retries FROM queue WHERE id=?",(entry_id,)).fetchone()
        if not row:return
        retries=row[0]+1; now=time.time()
        if retries>=max_retries: self._conn().execute("UPDATE queue SET status=?,retries=?,updated_at=?,upload_finished_at=?,error=? WHERE id=?",(Status.FAILED,retries,now,now,error,entry_id))
        else: self._conn().execute("UPDATE queue SET status=?,retries=?,next_retry_at=?,updated_at=?,error=? WHERE id=?",(Status.QUEUED,retries,now+min(backoff_base**retries,backoff_max),now,error,entry_id))
        self._conn().commit()

    def defer(self, entry_id: int, error: str, retry_after_seconds: float) -> None:
        self._conn().execute("UPDATE queue SET status=?,next_retry_at=?,updated_at=?,upload_finished_at=0,error=? WHERE id=?",(Status.QUEUED,time.time()+max(0,retry_after_seconds),time.time(),error,entry_id)); self._conn().commit()

    def requeue_failed(self, reset_retries: bool=True) -> int:
        cur=self._conn().execute("UPDATE queue SET status=?,retries=CASE WHEN ? THEN 0 ELSE retries END,next_retry_at=0,progress_percent=0,uploaded_bytes=0,updated_at=?,upload_started_at=0,upload_finished_at=0,upload_session_uri='',error=NULL WHERE status=?",(Status.QUEUED,reset_retries,time.time(),Status.FAILED)); self._conn().commit(); return cur.rowcount

    def stats(self) -> dict[str,int]: return {r[0]:r[1] for r in self._conn().execute("SELECT status,COUNT(*) FROM queue GROUP BY status")}
    def queued_breakdown(self) -> dict[str,int]:
        now=time.time(); row=self._conn().execute("SELECT SUM(next_retry_at<=?),SUM(next_retry_at>?) FROM queue WHERE status=?",(now,now,Status.QUEUED)).fetchone(); return {"ready":int(row[0] or 0),"waiting":int(row[1] or 0)}
    def pending_count(self) -> int: return self._conn().execute("SELECT COUNT(*) FROM queue WHERE status IN (?,?)",(Status.QUEUED,Status.UPLOADING)).fetchone()[0]
    def recent(self, limit:int=10) -> list[QueueEntry]: return [self._row_to_entry(r) for r in self._conn().execute("SELECT * FROM queue ORDER BY updated_at DESC,created_at DESC LIMIT ?",(limit,))]

    def create_multipart(self, queue_id:int, upload_id:str, bucket:str, object_key:str, part_size:int, source_size:int, source_blake3:str) -> None:
        now=time.time(); self._conn().execute("INSERT OR REPLACE INTO s3_multipart_uploads VALUES(?,?,?,?,?,?,?,?,?)",(queue_id,upload_id,bucket,object_key,part_size,source_size,source_blake3,now,now)); self._conn().commit()
    def get_multipart(self, queue_id:int) -> MultipartUpload|None:
        r=self._conn().execute("SELECT * FROM s3_multipart_uploads WHERE queue_id=?",(queue_id,)).fetchone(); return MultipartUpload(**dict(r)) if r else None
    def upsert_part(self, queue_id:int, part_number:int, etag:str, size_bytes:int) -> None:
        self._conn().execute("INSERT INTO s3_multipart_parts VALUES(?,?,?,?,?) ON CONFLICT(queue_id,part_number) DO UPDATE SET etag=excluded.etag,size_bytes=excluded.size_bytes,updated_at=excluded.updated_at",(queue_id,part_number,etag,size_bytes,time.time())); self._conn().execute("UPDATE s3_multipart_uploads SET updated_at=? WHERE queue_id=?",(time.time(),queue_id)); self._conn().commit()
    def get_parts(self, queue_id:int) -> list[MultipartPart]: return [MultipartPart(**dict(r)) for r in self._conn().execute("SELECT * FROM s3_multipart_parts WHERE queue_id=? ORDER BY part_number",(queue_id,))]
    def replace_parts(self, queue_id:int, parts:list[tuple[int,str,int]]) -> None:
        with self._lock:
            c=self._conn(); c.execute("BEGIN IMMEDIATE"); c.execute("DELETE FROM s3_multipart_parts WHERE queue_id=?",(queue_id,)); now=time.time(); c.executemany("INSERT INTO s3_multipart_parts VALUES(?,?,?,?,?)",[(queue_id,n,e,z,now) for n,e,z in parts]); c.commit()
    def clear_multipart(self, queue_id:int) -> None:
        self._conn().execute("DELETE FROM s3_multipart_uploads WHERE queue_id=?",(queue_id,)); self._conn().commit()
