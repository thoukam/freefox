from __future__ import annotations

import time
from pathlib import Path

import pytest

from freefox.watcher import FileWatcher


@pytest.fixture
def watcher_factory(tmp_path):
    def _create(
        extensions: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
        stable_seconds: float = 0.05,
        callback=None,
    ) -> tuple[FileWatcher, list[Path]]:
        called: list[Path] = []
        cb = callback if callback is not None else called.append
        watcher = FileWatcher(
            directory=tmp_path,
            extensions=extensions if extensions is not None else [".mcap", ".db3"],
            ignore_patterns=ignore_patterns
            if ignore_patterns is not None
            else ["*.active", "*.tmp", "metadata.yaml"],
            stable_seconds=stable_seconds,
            callback=cb,
        )
        return watcher, called

    return _create


def test_is_interesting_accepted_extensions(watcher_factory, tmp_path):
    watcher, _ = watcher_factory()
    assert watcher._is_interesting(tmp_path / "recording.mcap")
    assert watcher._is_interesting(tmp_path / "recording.db3")
    assert watcher._is_interesting(tmp_path / "RECORDING.MCAP")
    assert watcher._is_interesting(tmp_path / "RECORDING.DB3")


def test_is_interesting_rejected_extensions(watcher_factory, tmp_path):
    watcher, _ = watcher_factory()
    assert not watcher._is_interesting(tmp_path / "notes.txt")
    assert not watcher._is_interesting(tmp_path / "config.yaml")
    assert not watcher._is_interesting(tmp_path / "recording.bag")
    assert not watcher._is_interesting(tmp_path / "recording")


def test_is_interesting_ignore_patterns(watcher_factory, tmp_path):
    watcher, _ = watcher_factory()
    assert not watcher._is_interesting(tmp_path / "recording.mcap.active")
    assert not watcher._is_interesting(tmp_path / "recording.mcap.tmp")
    assert not watcher._is_interesting(tmp_path / "metadata.yaml")

    custom_watcher, _ = watcher_factory(ignore_patterns=["skip_*", "*.draft.mcap"])
    assert not custom_watcher._is_interesting(tmp_path / "skip_test.mcap")
    assert not custom_watcher._is_interesting(tmp_path / "foo.draft.mcap")
    assert custom_watcher._is_interesting(tmp_path / "valid.mcap")


def test_scan_finds_files_recursively(watcher_factory, tmp_path):
    watcher, called = watcher_factory(stable_seconds=0.01)
    sub = tmp_path / "deep" / "nested" / "dir"
    sub.mkdir(parents=True)
    f = sub / "session.mcap"
    f.write_bytes(b"content")

    watcher._scan()
    time.sleep(0.02)
    watcher._scan()

    assert called == [f]


def test_stable_file_triggers_callback_exactly_once(watcher_factory, tmp_path):
    watcher, called = watcher_factory(stable_seconds=0.01)
    f1 = tmp_path / "file1.mcap"
    f2 = tmp_path / "file2.db3"
    f1.write_bytes(b"data1")
    f2.write_bytes(b"data2")

    watcher._scan()
    time.sleep(0.02)
    watcher._scan()

    assert len(called) == 2
    assert set(called) == {f1, f2}

    # Subsequent scans do not re-trigger callback
    watcher._scan()
    watcher._scan()
    assert len(called) == 2


def test_unstable_file_does_not_trigger_callback(watcher_factory, tmp_path):
    watcher, called = watcher_factory(stable_seconds=0.1)
    f = tmp_path / "growing.mcap"
    f.write_bytes(b"initial")

    watcher._scan()
    f.write_bytes(b"initial + more data")
    time.sleep(0.05)
    watcher._scan()

    assert called == []


def test_ignored_files_skipped_in_scan(watcher_factory, tmp_path):
    watcher, called = watcher_factory(stable_seconds=0.01)
    (tmp_path / "file.txt").write_bytes(b"text")
    (tmp_path / "data.active").write_bytes(b"active")
    (tmp_path / "metadata.yaml").write_bytes(b"yaml")
    valid = tmp_path / "valid.mcap"
    valid.write_bytes(b"bag")

    watcher._scan()
    time.sleep(0.02)
    watcher._scan()

    assert called == [valid]
