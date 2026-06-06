"""Lance un smoke test Google Drive de bout en bout avec le vrai backend."""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from freefox.config import CollectorConfig
from freefox.queue import UploadQueue
from freefox.watcher import FileWatcher
from freefox.worker import UploadWorkerPool


def _build_remote_prefix(robot_id: str) -> str:
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{robot_id}/smoke-tests/{stamp}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload un petit fichier .mcap de demo vers Google Drive avec FreeFox.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="/etc/freefox/config.yaml",
        help="Chemin vers la configuration YAML FreeFox (defaut: /etc/freefox/config.yaml)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Secondes a attendre avant timeout de l'upload (defaut: 60)",
    )
    args = parser.parse_args()

    config = CollectorConfig.from_yaml(args.config)

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from freefox.backends.gdrive import GoogleDriveBackend

    root = Path(tempfile.mkdtemp(prefix="freefox-gdrive-smoke-"))
    watch_dir = root / "bags"
    queue_db = root / "queue.db"
    watch_dir.mkdir()

    queue = UploadQueue(queue_db)
    backend = GoogleDriveBackend(
        credentials_file=config.drive.credentials_file,
        target_folder_id=config.drive.target_folder_id,
    )
    remote_prefix = _build_remote_prefix(config.robot_id)

    def on_ready(path: Path) -> None:
        queue.add(path, f"{remote_prefix}/{path.name}")

    watcher = FileWatcher(
        directory=watch_dir,
        extensions=[".mcap"],
        ignore_patterns=["*.active", "*.tmp"],
        stable_seconds=1.0,
        callback=on_ready,
        poll_interval=0.25,
    )
    pool = UploadWorkerPool(queue, backend, config.upload)

    print(f"Espace de test:  {root}")
    print(f"Identifiants:    {config.drive.credentials_file}")
    print(f"Dossier Drive:   {config.drive.target_folder_id or 'racine'}")
    print(f"Prefixe distant: {remote_prefix}")

    watcher.start()
    pool.start()

    bag = watch_dir / "freefox-gdrive-smoke.mcap"
    try:
        print("Ecriture de freefox-gdrive-smoke.mcap en plusieurs morceaux...")
        with bag.open("wb") as fh:
            fh.write(b"freefox google drive smoke test\n")
            fh.flush()
            time.sleep(0.5)
            fh.write(f"created_at={datetime.datetime.now(datetime.UTC).isoformat()}\n".encode())
            fh.flush()

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            stats = queue.stats()
            if stats.get("done", 0) == 1:
                print("Upload termine.")
                print(f"Stats file:      {stats}")
                print(f"Chemin Drive:    {remote_prefix}/{bag.name}")
                return
            if stats.get("failed", 0):
                raise RuntimeError(f"Upload en echec: {stats}")
            time.sleep(0.5)

        raise TimeoutError(f"Delai depasse en attente de l'upload. Stats file: {queue.stats()}")
    finally:
        watcher.stop()
        pool.stop(drain_timeout=10)


if __name__ == "__main__":
    main()
