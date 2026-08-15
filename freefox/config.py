"""Configuration loader — reads YAML, validates, exposes typed dataclass."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


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
    # Calculate a BLAKE3 fingerprint before upload and store it in Drive metadata.
    verify_blake3: bool = True
    # Skip upload when a remote file with the same BLAKE3 already exists.
    deduplicate_by_hash: bool = True
    # Delete local file after successful upload
    delete_after_upload: bool = False


@dataclass
class StorageConfig:
    backend: Literal["gdrive", "rsync", "s3"] = "gdrive"
    legacy_backend: Literal["gdrive", "rsync"] | None = None


@dataclass
class DriveConfig:
    # Path to service-account JSON or OAuth2 credentials file
    credentials_file: Path = Path("credentials.json")
    # Shared Drive ID or "My Drive" folder ID to upload into
    target_folder_id: str = ""
    # Organise uploads as <folder>/<robot_id>/<YYYY-MM-DD>/<filename>
    use_date_subfolder: bool = True


@dataclass
class RsyncConfig:
    # Destination rsync: local path, user@host:/path, or rsync://host/module.
    destination: str = ""
    # Command used for remote shell destinations.
    ssh_command: str = "ssh"
    # Options passed before source/destination.
    options: list[str] = field(
        default_factory=lambda: [
            "--archive",
            "--partial",
            "--inplace",
            "--mkpath",
            "--info=progress2",
        ]
    )
    # Organise uploads as <destination>/<robot_id>/<YYYY-MM-DD>/<filename>
    use_date_subfolder: bool = True


@dataclass
class S3Config:
    bucket: str = ""
    object_prefix: str = ""
    region: str = ""
    endpoint_url: str = ""
    profile: str = ""
    addressing_style: Literal["auto", "path", "virtual"] = "auto"
    ca_bundle: Path | None = None
    use_date_subfolder: bool = True

    def validate(self, selected: bool = False) -> None:
        if selected and not self.bucket.strip():
            raise ValueError("s3.bucket est obligatoire pour le backend s3")
        prefix = self.object_prefix.strip("/")
        if any(part in {"", ".", ".."} for part in prefix.split("/")) and prefix:
            raise ValueError("s3.object_prefix contient un segment invalide")
        self.object_prefix = prefix
        if self.endpoint_url:
            parsed = urlparse(self.endpoint_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("s3.endpoint_url doit etre une URL HTTP(S) absolue")
        if self.addressing_style not in {"auto", "path", "virtual"}:
            raise ValueError("s3.addressing_style doit etre auto, path ou virtual")
        if self.endpoint_url and self.addressing_style == "auto":
            self.addressing_style = "path"
        if self.ca_bundle is not None and not self.ca_bundle.is_file():
            raise ValueError(f"s3.ca_bundle est illisible: {self.ca_bundle}")

    def snapshot(self) -> dict[str, object]:
        return {
            "bucket": self.bucket,
            "object_prefix": self.object_prefix,
            "region": self.region,
            "endpoint_url": self.endpoint_url,
            "profile": self.profile,
            "addressing_style": self.addressing_style,
            "ca_bundle": str(self.ca_bundle) if self.ca_bundle else "",
            "use_date_subfolder": self.use_date_subfolder,
        }


@dataclass
class CollectorConfig:
    robot_id: str
    watch: WatchConfig
    upload: UploadConfig
    storage: StorageConfig
    drive: DriveConfig
    rsync: RsyncConfig
    s3: S3Config
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
            retry_failed_on_start=_as_bool(upload_raw.get("retry_failed_on_start"), True),
            verify_blake3=_as_bool(upload_raw.get("verify_blake3"), True),
            deduplicate_by_hash=_as_bool(upload_raw.get("deduplicate_by_hash"), True),
            delete_after_upload=_as_bool(upload_raw.get("delete_after_upload"), False),
        )

        storage_raw = raw.get("storage", {})
        storage_backend = storage_raw.get("backend", raw.get("backend", "gdrive"))
        if storage_backend not in {"gdrive", "rsync", "s3"}:
            raise ValueError(f"Backend de stockage inconnu: {storage_backend}")
        legacy_backend = storage_raw.get("legacy_backend")
        if legacy_backend not in {None, "gdrive", "rsync"}:
            raise ValueError("storage.legacy_backend doit etre gdrive ou rsync")
        storage = StorageConfig(backend=storage_backend, legacy_backend=legacy_backend)

        drive_raw = raw.get("drive", {})
        drive = DriveConfig(
            credentials_file=Path(
                os.environ.get("FREEFOX_CREDENTIALS")
                or os.environ.get("ROSBAG_COLLECTOR_CREDENTIALS")
                or drive_raw.get("credentials_file", "credentials.json")
            ),
            target_folder_id=drive_raw.get("target_folder_id", ""),
            use_date_subfolder=_as_bool(drive_raw.get("use_date_subfolder"), True),
        )

        rsync_raw = raw.get("rsync", {})
        rsync = RsyncConfig(
            destination=rsync_raw.get("destination", ""),
            ssh_command=rsync_raw.get("ssh_command", "ssh"),
            options=rsync_raw.get(
                "options",
                [
                    "--archive",
                    "--partial",
                    "--inplace",
                    "--mkpath",
                    "--info=progress2",
                ],
            ),
            use_date_subfolder=_as_bool(rsync_raw.get("use_date_subfolder"), True),
        )

        s3_raw = raw.get("s3", {})
        forbidden = {"access_key", "access_key_id", "secret_key", "secret_access_key", "session_token"}
        present = sorted(forbidden.intersection(s3_raw))
        if present:
            raise ValueError("Les secrets S3 ne sont pas autorises dans YAML: " + ", ".join(present))
        ca_value = s3_raw.get("ca_bundle")
        s3 = S3Config(
            bucket=str(s3_raw.get("bucket", "")).strip(),
            object_prefix=str(s3_raw.get("object_prefix", "")),
            region=str(s3_raw.get("region", "")),
            endpoint_url=str(s3_raw.get("endpoint_url", "")),
            profile=str(s3_raw.get("profile", "")),
            addressing_style=str(s3_raw.get("addressing_style", "auto")),
            ca_bundle=Path(ca_value) if ca_value else None,
            use_date_subfolder=_as_bool(s3_raw.get("use_date_subfolder"), True),
        )
        s3.validate(selected=storage_backend == "s3")

        queue_db = Path(raw.get("queue_db", "/var/lib/freefox/queue.db"))
        log_level = raw.get("log_level", "INFO").upper()

        return cls(
            robot_id=robot_id,
            watch=watch,
            upload=upload,
            storage=storage,
            drive=drive,
            rsync=rsync,
            s3=s3,
            queue_db=queue_db,
            log_level=log_level,
        )
