"""Lazy backend registry."""
from __future__ import annotations
import json
from pathlib import Path
from freefox.backends import StorageBackend
from freefox.config import CollectorConfig, S3Config


class BackendRegistry:
    def __init__(self, config: CollectorConfig) -> None:
        self.config=config; self._cache: dict[tuple[str,str],StorageBackend]={}

    def get(self, backend: str, destination: dict | None=None) -> StorageBackend:
        destination=destination or {}; key=(backend,json.dumps(destination,sort_keys=True))
        if key in self._cache:return self._cache[key]
        if backend=="gdrive":
            from freefox.backends.gdrive import GoogleDriveBackend
            obj=GoogleDriveBackend(destination.get("credentials_file",self.config.drive.credentials_file), destination.get("target_folder_id",self.config.drive.target_folder_id))
        elif backend=="rsync":
            from freefox.backends.rsync import RsyncBackend
            obj=RsyncBackend(destination.get("destination",self.config.rsync.destination), destination.get("options",self.config.rsync.options), destination.get("ssh_command",self.config.rsync.ssh_command))
        elif backend=="s3":
            from freefox.backends.s3 import S3Backend
            values=self.config.s3.snapshot(); values.update(destination)
            ca=values.get("ca_bundle") or None
            if ca: ca=Path(ca)
            cfg=S3Config(**{**values,"ca_bundle":ca}); cfg.validate(selected=True); obj=S3Backend(cfg)
        else: raise ValueError(f"Backend de stockage inconnu: {backend}")
        self._cache[key]=obj; return obj


def build_backend(config: CollectorConfig) -> StorageBackend:
    return BackendRegistry(config).get(config.storage.backend, _snapshot(config, config.storage.backend))


def _snapshot(config: CollectorConfig, backend: str) -> dict:
    if backend=="s3": return config.s3.snapshot()
    if backend=="rsync": return {"destination":config.rsync.destination,"options":config.rsync.options,"ssh_command":config.rsync.ssh_command,"use_date_subfolder":config.rsync.use_date_subfolder}
    return {"credentials_file":str(config.drive.credentials_file),"target_folder_id":config.drive.target_folder_id,"use_date_subfolder":config.drive.use_date_subfolder}
