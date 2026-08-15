"""Provider-neutral storage backend contracts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

ProgressCallback = Callable[[float, int], None]
SessionCallback = Callable[[str], None]
BackendName = str


class Inspection(str, Enum):
    MISSING = "missing"
    IDENTICAL = "identical"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class UploadResult:
    location: str
    size_bytes: int
    blake3_digest: str = ""
    deduplicated: bool = False


class BackendError(RuntimeError):
    """Base provider-neutral backend error."""


class TransientBackendError(BackendError):
    pass


class QuotaBackendError(TransientBackendError):
    pass


class TransientCredentialError(TransientBackendError):
    pass


class AuthenticationBackendError(BackendError):
    pass


class ConfigurationBackendError(BackendError):
    pass


class ConflictBackendError(BackendError):
    pass


class InvalidSessionError(TransientBackendError):
    pass


@dataclass(frozen=True)
class DestinationSnapshot:
    backend: BackendName
    settings: dict[str, Any]


class StorageBackend(Protocol):
    def exists(self, remote_path: str) -> bool: ...
    def find_duplicate(self, remote_path: str, blake3_digest: str, size_bytes: int) -> bool: ...
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
    ) -> str: ...
