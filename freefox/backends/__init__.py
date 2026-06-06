"""Storage backend interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

ProgressCallback = Callable[[float, int], None]
SessionCallback = Callable[[str], None]


class StorageBackend(Protocol):
    """Backend contract used by upload workers."""

    def exists(self, remote_path: str) -> bool:
        """Return True when the remote object already exists."""

    def upload(
        self,
        local_path: Path,
        remote_path: str,
        chunk_size: int = 2 * 1024 * 1024,
        progress_callback: ProgressCallback | None = None,
        session_uri: str = "",
        session_callback: SessionCallback | None = None,
    ) -> str:
        """Upload a file and return a backend-specific location/link."""
