"""File watcher — detects new completed rosbags in a directory.

Strategy
--------
1. Try inotify (Linux, low overhead) via *watchdog*.
2. Fall back to polling every `poll_interval` seconds.

A file is considered "complete" when its size has not changed for
`stable_seconds` consecutive seconds AND it is not held open by any
process (checked via /proc on Linux).
"""

from __future__ import annotations

import fnmatch
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Callback type: called with the completed file path
OnFile = Callable[[Path], None]


def _is_open(path: Path) -> bool:
    """Return True if any process has *path* open (Linux /proc check)."""
    try:
        target = str(path.resolve())
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            fd_dir = f"/proc/{pid}/fd"
            try:
                for fd in os.listdir(fd_dir):
                    try:
                        link = os.readlink(f"{fd_dir}/{fd}")
                        if link == target:
                            return True
                    except OSError:
                        pass
            except PermissionError:
                pass
    except Exception:
        pass
    return False


class StabilityTracker:
    """Tracks file sizes over time to detect when writing has stopped."""

    def __init__(self, stable_seconds: float) -> None:
        self._stable_seconds = stable_seconds
        # path → (last_size, last_change_time)
        self._state: dict[str, tuple[int, float]] = {}

    def update(self, path: Path) -> bool:
        """Return True if *path* is stable and not open."""
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            self._state.pop(str(path), None)
            return False

        key = str(path)
        now = time.monotonic()
        prev_size, prev_time = self._state.get(key, (None, now))

        if prev_size != size:
            self._state[key] = (size, now)
            return False

        stable = (now - prev_time) >= self._stable_seconds
        if stable and _is_open(path):
            logger.debug("%s is stable but still open — waiting", path.name)
            return False

        return stable

    def forget(self, path: Path) -> None:
        self._state.pop(str(path), None)


class FileWatcher:
    """Watch *directory* and call *callback* for each completed bag file."""

    def __init__(
        self,
        directory: Path,
        extensions: list[str],
        ignore_patterns: list[str],
        stable_seconds: float,
        callback: OnFile,
        poll_interval: float = 2.0,
    ) -> None:
        self._directory = directory
        self._extensions = {ext.lower() for ext in extensions}
        self._ignore_patterns = ignore_patterns
        self._callback = callback
        self._poll_interval = poll_interval
        self._tracker = StabilityTracker(stable_seconds)
        self._seen: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_interesting(self, path: Path) -> bool:
        if path.suffix.lower() not in self._extensions:
            return False
        name = path.name
        for pattern in self._ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return False
        return True

    def _scan(self) -> None:
        try:
            paths = list(self._directory.rglob("*"))
        except Exception as exc:
            logger.warning("Scan error: %s", exc)
            return

        for path in paths:
            if not path.is_file():
                continue
            if not self._is_interesting(path):
                continue
            key = str(path)
            if key in self._seen:
                continue
            if self._tracker.update(path):
                self._seen.add(key)
                self._tracker.forget(path)
                logger.info("New bag ready: %s", path)
                try:
                    self._callback(path)
                except Exception as exc:
                    logger.error("Callback error for %s: %s", path, exc)

    def _run(self) -> None:
        logger.info(
            "Watcher started on %s (extensions: %s)",
            self._directory,
            self._extensions,
        )
        # Attempt to use watchdog for inotify events
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            watcher = self

            class Handler(FileSystemEventHandler):
                def on_created(self, event):
                    if not event.is_directory:
                        watcher._scan()

                def on_modified(self, event):
                    if not event.is_directory:
                        watcher._scan()

            observer = Observer()
            observer.schedule(Handler(), str(self._directory), recursive=True)
            observer.start()
            logger.debug("inotify observer started")
            while not self._stop.is_set():
                self._scan()
                self._stop.wait(self._poll_interval)
            observer.stop()
            observer.join()
        except ImportError:
            logger.warning("watchdog not installed — using polling only")
            while not self._stop.is_set():
                self._scan()
                self._stop.wait(self._poll_interval)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, daemon=True, name="watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
