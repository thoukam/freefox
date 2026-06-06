"""Configuration loader — reads YAML, validates, exposes typed dataclass."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


@dataclass
class WatchConfig:
    directory: Path
    # Seconds a file must be stable (no size change) before considered complete.
    # Covers bags closed via duration/size split or manual SIGINT.
    stable_seconds: float = 5.0
    extensions: list[str] = field(default_factory=lambda: [".mcap", ".db3"])
    # Glob patterns to ignore (e.g. active recording metadata)
    ignore_patterns: list[str] = field(default_factory=lambda: ["*.active", "*.tmp"])


@dataclass
class UploadConfig:
    # Max concurrent uploads
    workers: int = 2
    # Chunk size for resumable uploads (bytes). Google Drive min = 256 KiB.
    chunk_size: int = 256 * 1024 * 8  # 2 MiB
    # Retry policy
    max_retries: int = 10
    retry_backoff_base: float = 2.0   # seconds, exponential
    retry_backoff_max: float = 300.0  # 5 min cap
    # Delay before retrying quota-related provider errors.
    quota_retry_delay: float = 60.0
    # Delay before retrying transient network errors.
    transient_retry_delay: float = 60.0
    # Retry failed queue entries automatically when the service starts.
    retry_failed_on_start: bool = True
    # Delete local file after successful upload
    delete_after_upload: bool = False


@dataclass
class DriveConfig:
    # Path to service-account JSON or OAuth2 credentials file
    credentials_file: Path = Path("credentials.json")
    # Shared Drive ID or "My Drive" folder ID to upload into
    target_folder_id: str = ""
    # Organise uploads as <folder>/<robot_id>/<YYYY-MM-DD>/<filename>
    use_date_subfolder: bool = True


@dataclass
class CollectorConfig:
    robot_id: str
    watch: WatchConfig
    upload: UploadConfig
    drive: DriveConfig
    # Path to SQLite queue database
    queue_db: Path = Path("/var/lib/freefox/queue.db")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CollectorConfig":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        # Allow env-var override for robot_id (useful in containers / CI)
        robot_id = (
            os.environ.get("FREEFOX_ROBOT_ID")
            or os.environ.get("ROSBAG_COLLECTOR_ROBOT_ID")
        ) or raw.get(
            "robot_id", socket.gethostname()
        )

        watch_raw = raw.get("watch", {})
        watch = WatchConfig(
            directory=Path(watch_raw["directory"]),
            stable_seconds=float(watch_raw.get("stable_seconds", 5.0)),
            extensions=watch_raw.get("extensions", [".mcap", ".db3"]),
            ignore_patterns=watch_raw.get("ignore_patterns", ["*.active", "*.tmp"]),
        )

        upload_raw = raw.get("upload", {})
        upload = UploadConfig(
            workers=int(upload_raw.get("workers", 2)),
            chunk_size=int(upload_raw.get("chunk_size", 256 * 1024 * 8)),
            max_retries=int(upload_raw.get("max_retries", 10)),
            retry_backoff_base=float(upload_raw.get("retry_backoff_base", 2.0)),
            retry_backoff_max=float(upload_raw.get("retry_backoff_max", 300.0)),
            quota_retry_delay=float(upload_raw.get("quota_retry_delay", 60.0)),
            transient_retry_delay=float(upload_raw.get("transient_retry_delay", 60.0)),
            retry_failed_on_start=bool(upload_raw.get("retry_failed_on_start", True)),
            delete_after_upload=bool(upload_raw.get("delete_after_upload", False)),
        )

        drive_raw = raw.get("drive", {})
        drive = DriveConfig(
            credentials_file=Path(
                os.environ.get("FREEFOX_CREDENTIALS")
                or os.environ.get("ROSBAG_COLLECTOR_CREDENTIALS")
                or drive_raw.get("credentials_file", "credentials.json")
            ),
            target_folder_id=drive_raw.get("target_folder_id", ""),
            use_date_subfolder=bool(drive_raw.get("use_date_subfolder", True)),
        )

        queue_db = Path(raw.get("queue_db", "/var/lib/freefox/queue.db"))
        log_level = raw.get("log_level", "INFO").upper()

        return cls(
            robot_id=robot_id,
            watch=watch,
            upload=upload,
            drive=drive,
            queue_db=queue_db,
            log_level=log_level,
        )
