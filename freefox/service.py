"""Collector service wiring watcher, durable queue and backend registry."""

from __future__ import annotations

import datetime
import logging
import signal
import sys
from pathlib import Path
from typing import TextIO

from freefox.backends.factory import BackendRegistry, _snapshot
from freefox.config import CollectorConfig
from freefox.queue import UploadQueue
from freefox.watcher import FileWatcher
from freefox.worker import UploadWorkerPool

logger = logging.getLogger(__name__)


def _build_remote_path(config: CollectorConfig, local_path: Path) -> str:
    if config.storage.backend == "rsync":
        use_date = config.rsync.use_date_subfolder
        prefix = ""
    elif config.storage.backend == "s3":
        use_date = config.s3.use_date_subfolder
        prefix = config.s3.object_prefix
    else:
        use_date = config.drive.use_date_subfolder
        prefix = ""
    parts = [p for p in (prefix, config.robot_id) if p]
    if use_date:
        parts.append(datetime.date.today().isoformat())
    parts.append(local_path.name)
    return "/".join(parts)


class CollectorService:
    def __init__(self, config: CollectorConfig) -> None:
        self._config = config
        legacy = (
            config.storage.backend
            if config.storage.backend in {"gdrive", "rsync"}
            else config.storage.legacy_backend
        )
        legacy_dest = _snapshot(config, legacy) if legacy else {}
        self._queue = UploadQueue(
            config.queue_db, legacy_backend=legacy, legacy_destination=legacy_dest
        )
        self._registry = BackendRegistry(config)
        self._watcher = FileWatcher(
            directory=config.watch.directory,
            extensions=config.watch.extensions,
            ignore_patterns=config.watch.ignore_patterns,
            stable_seconds=config.watch.stable_seconds,
            callback=self._on_new_bag,
        )
        self._pool = UploadWorkerPool(
            queue=self._queue,
            registry=self._registry,
            config=config.upload,
            delete_after=config.upload.delete_after_upload,
        )
        self._running = False

    def _on_new_bag(self, path: Path) -> None:
        backend = self._config.storage.backend
        entry = self._queue.add(
            path,
            _build_remote_path(self._config, path),
            backend=backend,
            destination=_snapshot(self._config, backend),
        )
        if entry:
            logger.info("Queued: %s -> %s backend=%s", path.name, entry.remote_path, backend)

    def run(self) -> None:
        self._running = True
        if self._config.upload.retry_failed_on_start:
            restored = self._queue.requeue_failed()
            if restored:
                logger.info("%d failed transfers requeued", restored)

        def shutdown(signum, _frame):
            logger.info("Signal %d received", signum)
            self.stop()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        self._watcher.start()
        self._pool.start()
        import time

        try:
            while self._running:
                time.sleep(30)
                logger.info(
                    "Queue stats: %s queued=%s", self._queue.stats(), self._queue.queued_breakdown()
                )
        except SystemExit:
            pass

    def stop(self) -> None:
        self._running = False
        self._watcher.stop()
        self._pool.stop()
        logger.info("freefox stopped")
        sys.exit(0)


def check_config(
    config_path: str | Path,
    registry: BackendRegistry | None = None,
    stream: TextIO | None = None,
) -> int:
    if stream is None:
        stream = sys.stdout
    path = Path(config_path)
    print(f"Checking configuration: {path}", file=stream)

    # 1. Load and validate the YAML
    try:
        config = CollectorConfig.from_yaml(path)
        print("  [OK] YAML syntax and schema valid", file=stream)
    except Exception as exc:
        print(f"  [FAIL] Configuration error: {exc}", file=sys.stderr)
        return 1

    # 2. Check that watch.directory exists and is readable
    watch_dir = config.watch.directory
    try:
        if not watch_dir.exists():
            print(f"  [FAIL] Watch directory does not exist: {watch_dir}", file=sys.stderr)
            return 1
        if not watch_dir.is_dir():
            print(f"  [FAIL] Watch path is not a directory: {watch_dir}", file=sys.stderr)
            return 1
        list(watch_dir.iterdir())
        print(f"  [OK] Watch directory exists and is readable: {watch_dir}", file=stream)
    except Exception as exc:
        print(f"  [FAIL] Watch directory not readable ({watch_dir}): {exc}", file=sys.stderr)
        return 1

    # 3. Build backend and call exists("freefox-check") on it
    backend_name = config.storage.backend
    try:
        if registry is None:
            registry = BackendRegistry(config)
        backend = registry.get(backend_name, _snapshot(config, backend_name))
        backend.exists("freefox-check")
        print(f"  [OK] Storage backend '{backend_name}' reachable", file=stream)
    except Exception as exc:
        print(f"  [FAIL] Storage backend check failed ({backend_name}): {exc}", file=sys.stderr)
        return 1

    print("Configuration check passed.", file=stream)
    return 0


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="freefox", description="Automatically upload ROS 2 bags to cloud storage."
    )
    parser.add_argument("-c", "--config", default="/etc/freefox/config.yaml")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate the config and test the backend without starting the service",
    )
    args = parser.parse_args()

    if args.check_config:
        sys.exit(check_config(args.config))

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
