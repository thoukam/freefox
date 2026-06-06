"""Surveille un vrai dossier de bags et upload les fichiers termines vers Google Drive."""

from __future__ import annotations

import argparse
import datetime
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from freefox.config import CollectorConfig
from freefox.queue import UploadQueue
from freefox.watcher import FileWatcher
from freefox.worker import UploadWorkerPool


def _shorten(value: str, width: int = 48) -> str:
    if len(value) <= width:
        return value
    return "..." + value[-(width - 3):]


def _log_recent_queue(queue: UploadQueue) -> None:
    entries = queue.recent(limit=8)
    if not entries:
        logging.info("File vide")
        return

    logging.info("Entrees recentes de la file:")
    for entry in entries:
        logging.info(
            "  #%s %-9s %6.1f%% retries=%s %s%s",
            entry.id,
            entry.status.value,
            entry.progress_percent,
            entry.retries,
            _shorten(entry.remote_path),
            f" error={entry.error}" if entry.error else "",
        )


def _build_remote_path(config: CollectorConfig, local_path: Path) -> str:
    parts = [config.robot_id]
    if config.drive.use_date_subfolder:
        parts.append(datetime.date.today().isoformat())
    parts.append(local_path.name)
    return "/".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Surveille un dossier rosbag reel et upload les bags termines vers Google Drive.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="/etc/freefox/config.yaml",
        help="Chemin vers la configuration YAML FreeFox (defaut: /etc/freefox/config.yaml)",
    )
    args = parser.parse_args()

    config = CollectorConfig.from_yaml(args.config)

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from freefox.backends.gdrive import GoogleDriveBackend

    queue = UploadQueue(config.queue_db)
    backend = GoogleDriveBackend(
        credentials_file=config.drive.credentials_file,
        target_folder_id=config.drive.target_folder_id,
    )

    def on_ready(path: Path) -> None:
        remote_path = _build_remote_path(config, path)
        entry = queue.add(path, remote_path)
        if entry:
            logging.info("Ajoute a la file %s -> %s", path, remote_path)
        else:
            logging.info("Deja dans la file: %s", path)

    watcher = FileWatcher(
        directory=config.watch.directory,
        extensions=config.watch.extensions,
        ignore_patterns=config.watch.ignore_patterns,
        stable_seconds=config.watch.stable_seconds,
        callback=on_ready,
        poll_interval=1.0,
    )
    pool = UploadWorkerPool(queue, backend, config.upload)

    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f"Surveillance:    {config.watch.directory}")
    print(f"Base de file:    {config.queue_db}")
    print(f"Dossier Drive:   {config.drive.target_folder_id or 'racine'}")
    print(f"Robot ID:        {config.robot_id}")
    print("Ctrl-C pour arreter.")

    watcher.start()
    pool.start()

    try:
        while running:
            time.sleep(5)
            logging.info("Stats file: %s", queue.stats())
            _log_recent_queue(queue)
    finally:
        watcher.stop()
        pool.stop(drain_timeout=30)


if __name__ == "__main__":
    main()
