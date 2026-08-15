"""Lance un smoke test local de bout en bout sans identifiants Google Drive."""

from __future__ import annotations

import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from freefox.config import UploadConfig
from freefox.integrity import calculate_blake3
from freefox.queue import UploadQueue
from freefox.watcher import FileWatcher
from freefox.worker import UploadWorkerPool


class LocalBackend:
    """Backend utilise uniquement pour les smoke tests locaux."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def exists(self, remote_path: str) -> bool:
        return (self._root / remote_path).exists()

    def find_duplicate(
        self,
        remote_path: str,
        blake3_digest: str,
        size_bytes: int,
    ) -> bool:
        destination = self._root / remote_path
        if not destination.exists():
            return False
        return (
            destination.stat().st_size == size_bytes
            and calculate_blake3(destination) == blake3_digest
        )

    def upload(
        self,
        local_path: Path,
        remote_path: str,
        chunk_size: int = 2 * 1024 * 1024,
        progress_callback=None,
        session_uri: str = "",
        session_callback=None,
        blake3_digest: str = "",
        expected_size: int = 0,
    ) -> str:
        destination = self._root / remote_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        if progress_callback:
            progress_callback(100.0, local_path.stat().st_size)
        return str(destination)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root = Path(tempfile.mkdtemp(prefix="freefox-smoke-"))
    watch_dir = root / "bags"
    remote_dir = root / "remote"
    queue_db = root / "queue.db"
    watch_dir.mkdir()

    queue = UploadQueue(queue_db)
    backend = LocalBackend(remote_dir)
    upload_config = UploadConfig(workers=1, chunk_size=1024)

    def on_ready(path: Path) -> None:
        queue.add(path, f"robot-local/{path.name}")

    watcher = FileWatcher(
        directory=watch_dir,
        extensions=[".mcap", ".db3"],
        ignore_patterns=["*.active", "*.tmp"],
        stable_seconds=1.0,
        callback=on_ready,
        poll_interval=0.25,
    )
    pool = UploadWorkerPool(queue, backend, upload_config)

    print(f"Espace de test:  {root}")
    print(f"Surveillance:    {watch_dir}")
    print(f"Remote fictif:   {remote_dir}")

    watcher.start()
    pool.start()

    bag = watch_dir / "demo.mcap"
    try:
        print("Ecriture de demo.mcap en plusieurs morceaux...")
        with bag.open("wb") as fh:
            fh.write(b"first chunk\n")
            fh.flush()
            time.sleep(0.5)
            fh.write(b"second chunk\n")
            fh.flush()

        deadline = time.time() + 10
        uploaded = remote_dir / "robot-local" / bag.name
        while time.time() < deadline:
            if uploaded.exists():
                print(f"Copie uploadee:  {uploaded}")
                print(f"Stats file:      {queue.stats()}")
                return
            time.sleep(0.25)

        raise TimeoutError(f"Delai depasse en attente de l'upload: {uploaded}")
    finally:
        watcher.stop()
        pool.stop(drain_timeout=5)


if __name__ == "__main__":
    main()
