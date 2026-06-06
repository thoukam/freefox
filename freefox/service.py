"""Collector service — wires watcher, queue, and upload pool together."""

from __future__ import annotations

import datetime
import logging
import signal
import sys
from pathlib import Path

from freefox.config import CollectorConfig
from freefox.queue import UploadQueue
from freefox.watcher import FileWatcher
from freefox.worker import UploadWorkerPool

logger = logging.getLogger(__name__)


def _build_remote_path(config: CollectorConfig, local_path: Path) -> str:
    """Construct the remote path: <robot_id>[/<date>]/<filename>."""
    parts = [config.robot_id]
    if config.drive.use_date_subfolder:
        parts.append(datetime.date.today().isoformat())
    parts.append(local_path.name)
    return "/".join(parts)


class CollectorService:
    """Top-level service object — create, call run()."""

    def __init__(self, config: CollectorConfig) -> None:
        self._config = config
        self._queue = UploadQueue(config.queue_db)

        # Build backend (only Drive for now; future: S3, NAS, …)
        from freefox.backends.gdrive import GoogleDriveBackend

        self._backend = GoogleDriveBackend(
            credentials_file=config.drive.credentials_file,
            target_folder_id=config.drive.target_folder_id,
        )

        self._watcher = FileWatcher(
            directory=config.watch.directory,
            extensions=config.watch.extensions,
            ignore_patterns=config.watch.ignore_patterns,
            stable_seconds=config.watch.stable_seconds,
            callback=self._on_new_bag,
        )

        self._pool = UploadWorkerPool(
            queue=self._queue,
            backend=self._backend,
            config=config.upload,
            delete_after=config.upload.delete_after_upload,
        )

        self._running = False

    # ------------------------------------------------------------------
    # Watcher callback
    # ------------------------------------------------------------------

    def _on_new_bag(self, path: Path) -> None:
        remote = _build_remote_path(self._config, path)
        entry = self._queue.add(path, remote)
        if entry:
            logger.info("Queued: %s → %s", path.name, remote)
        else:
            logger.debug("Already queued: %s", path.name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._running = True
        logger.info(
            "freefox starting (robot_id=%s, watch=%s)",
            self._config.robot_id,
            self._config.watch.directory,
        )

        # Graceful shutdown on SIGTERM / SIGINT
        def _shutdown(signum, _frame):
            logger.info("Signal %d received — shutting down…", signum)
            self.stop()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        self._watcher.start()
        self._pool.start()

        # Log periodic stats
        import time

        try:
            while self._running:
                time.sleep(30)
                stats = self._queue.stats()
                logger.info("Queue stats: %s", stats)
        except SystemExit:
            pass

    def stop(self) -> None:
        self._running = False
        self._watcher.stop()
        self._pool.stop()
        logger.info("freefox stopped")
        sys.exit(0)


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="freefox",
        description="Automatically upload ROS 2 bags to cloud storage.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="/etc/freefox/config.yaml",
        help="Path to YAML config file (default: /etc/freefox/config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level from config",
    )
    args = parser.parse_args()

    config = CollectorConfig.from_yaml(args.config)
    if args.log_level:
        config.log_level = args.log_level

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    CollectorService(config).run()


if __name__ == "__main__":
    main()
