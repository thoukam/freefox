"""Backend rsync pour copier les bags vers un dossier local ou distant."""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from freefox.backends import ProgressCallback, SessionCallback, StorageBackend
from freefox.integrity import calculate_blake3

logger = logging.getLogger(__name__)

_REMOTE_RE = re.compile(r"^(?P<host>[^:]+):(?P<path>.+)$")


def _is_remote(destination: str) -> bool:
    return destination.startswith("rsync://") or bool(_REMOTE_RE.match(destination))


def _join_remote(destination: str, remote_path: str) -> str:
    if destination.startswith("rsync://"):
        return f"{destination.rstrip('/')}/{remote_path}"
    match = _REMOTE_RE.match(destination)
    if match:
        return f"{match.group('host')}:{match.group('path').rstrip('/')}/{remote_path}"
    return str(Path(destination) / remote_path)


def _remote_shell_parts(destination: str) -> tuple[str, str] | None:
    if destination.startswith("rsync://"):
        return None
    match = _REMOTE_RE.match(destination)
    if not match:
        return None
    return match.group("host"), match.group("path")


class RsyncBackend(StorageBackend):
    """Copie les fichiers avec rsync, en local ou via SSH."""

    def __init__(
        self,
        destination: str,
        options: list[str] | None = None,
        ssh_command: str = "ssh",
    ) -> None:
        if not destination:
            raise ValueError("rsync.destination est obligatoire pour le backend rsync")
        self._destination = destination
        self._options = options or [
            "--archive",
            "--partial",
            "--inplace",
            "--mkpath",
            "--info=progress2",
        ]
        self._ssh_command = ssh_command

    def exists(self, remote_path: str) -> bool:
        target = _join_remote(self._destination, remote_path)
        if not _is_remote(self._destination):
            return Path(target).exists()

        remote = _remote_shell_parts(self._destination)
        if not remote:
            return False
        host, base = remote
        full_path = f"{base.rstrip('/')}/{remote_path}"
        proc = subprocess.run(
            [*self._ssh_base(), host, "test", "-f", full_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return proc.returncode == 0

    def find_duplicate(
        self,
        remote_path: str,
        blake3_digest: str,
        size_bytes: int,
    ) -> bool:
        if not blake3_digest:
            return False
        target = _join_remote(self._destination, remote_path)
        sidecar = f"{target}.blake3"

        if not _is_remote(self._destination):
            target_path = Path(target)
            sidecar_path = Path(sidecar)
            if not target_path.exists() or not sidecar_path.exists():
                return False
            if target_path.stat().st_size != size_bytes:
                return False
            parts = sidecar_path.read_text().strip().split()
            return bool(parts) and parts[0] == blake3_digest

        remote = _remote_shell_parts(self._destination)
        if not remote:
            return False
        host, base = remote
        full_path = f"{base.rstrip('/')}/{remote_path}"
        sidecar_path = f"{full_path}.blake3"
        command = (
            f"test -f {shlex.quote(full_path)} "
            f"&& test -f {shlex.quote(sidecar_path)} "
            f"&& stat -c %s {shlex.quote(full_path)} "
            f"&& cat {shlex.quote(sidecar_path)}"
        )
        proc = subprocess.run(
            [*self._ssh_base(), host, command],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode != 0:
            return False
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if len(lines) < 2:
            return False
        try:
            remote_size = int(lines[0])
        except ValueError:
            return False
        parts = lines[1].split()
        return remote_size == size_bytes and bool(parts) and parts[0] == blake3_digest

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
        del chunk_size, session_uri, session_callback
        file_size = local_path.stat().st_size
        if expected_size and expected_size != file_size:
            raise RuntimeError(
                f"Local file size changed before rsync: {expected_size} -> {file_size}"
            )

        target = _join_remote(self._destination, remote_path)
        logger.info("rsync %s -> %s", local_path.name, target)
        self._run_rsync(local_path, target, file_size, progress_callback)

        if blake3_digest:
            self._upload_sidecar(remote_path, blake3_digest, file_size)
            if not self.find_duplicate(remote_path, blake3_digest, file_size):
                raise RuntimeError("rsync integrity metadata mismatch")
        elif progress_callback:
            progress_callback(100.0, file_size)

        return target

    def _run_rsync(
        self,
        source: Path,
        target: str,
        file_size: int,
        progress_callback: ProgressCallback | None,
    ) -> None:
        cmd = ["rsync", *self._options]
        if _remote_shell_parts(self._destination):
            cmd.extend(["-e", self._ssh_command])
        cmd.extend([str(source), target])
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("rsync est introuvable sur cette machine") from exc

        assert proc.stdout is not None
        for line in proc.stdout:
            if progress_callback:
                pct = _parse_progress_percent(line)
                if pct is not None:
                    progress_callback(pct, int(file_size * (pct / 100.0)))

        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"rsync a echoue avec le code {code}")
        if progress_callback:
            progress_callback(100.0, file_size)

    def _upload_sidecar(
        self,
        remote_path: str,
        blake3_digest: str,
        file_size: int,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="freefox-rsync-") as tmp:
            sidecar = Path(tmp) / f"{Path(remote_path).name}.blake3"
            sidecar.write_text(f"{blake3_digest}  {file_size}\n")
            self._run_rsync(
                sidecar,
                f"{_join_remote(self._destination, remote_path)}.blake3",
                sidecar.stat().st_size,
                None,
            )

    def _ssh_base(self) -> list[str]:
        return shlex.split(self._ssh_command)


def _parse_progress_percent(line: str) -> float | None:
    match = re.search(r"\b(\d{1,3})%", line)
    if not match:
        return None
    return max(0.0, min(100.0, float(match.group(1))))
