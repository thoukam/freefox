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

    def find_duplicate(
        self,
        remote_path: str,
        blake3_digest: str,
        size_bytes: int,
    ) -> bool:
        """Return True when an equivalent remote object already exists."""

    def upload(
        self,
        local_path: Path,
        remote_path: str,
        chunk_size: int = 2 * 1024 * 1024,
        progress_callback: ProgressCallback | None = None,
        session_uri: str = "",
        session_callback: SessionCallback | None = None,
        blake3_digest: str = "",
        expected_size: int = 0,
    ) -> str:
        """Upload a file and return a backend-specific location/link."""
