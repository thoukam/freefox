"""Creation du backend de stockage configure."""

from __future__ import annotations

from freefox.backends import StorageBackend
from freefox.config import CollectorConfig


def build_backend(config: CollectorConfig) -> StorageBackend:
    if config.storage.backend == "gdrive":
        from freefox.backends.gdrive import GoogleDriveBackend

        return GoogleDriveBackend(
            credentials_file=config.drive.credentials_file,
            target_folder_id=config.drive.target_folder_id,
        )

    if config.storage.backend == "rsync":
        from freefox.backends.rsync import RsyncBackend

        return RsyncBackend(
            destination=config.rsync.destination,
            options=config.rsync.options,
            ssh_command=config.rsync.ssh_command,
        )

    raise ValueError(f"Backend de stockage inconnu: {config.storage.backend}")
