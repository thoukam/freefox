from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from freefox.backends import StorageBackend
from freefox.service import check_config, main


class FakeBackend(StorageBackend):
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.checked: list[str] = []

    def exists(self, remote_path: str) -> bool:
        if self.should_fail:
            raise ConnectionError("Cannot reach remote storage")
        self.checked.append(remote_path)
        return False

    def upload(self, local_path: Path, remote_path: str, progress_callback=None) -> None:
        pass


def _write_config(path: Path, watch_dir: Path, backend: str = "rsync") -> None:
    content = f"""
robot_id: test-bot
watch:
  directory: {watch_dir}
  stable_seconds: 1.0
upload:
  workers: 1
storage:
  backend: {backend}
rsync:
  destination: /tmp/dest
queue_db: {path.parent / "queue.db"}
"""
    path.write_text(content.strip(), encoding="utf-8")


def test_check_config_invalid_yaml(tmp_path, capsys):
    bad_cfg = tmp_path / "bad_config.yaml"
    bad_cfg.write_text("invalid: yaml: [unclosed", encoding="utf-8")

    code = check_config(bad_cfg)
    assert code == 1

    captured = capsys.readouterr()
    assert "[FAIL] Configuration error" in captured.err


def test_check_config_missing_watch_directory(tmp_path, capsys):
    cfg_file = tmp_path / "config.yaml"
    non_existent_watch = tmp_path / "no_such_dir"
    _write_config(cfg_file, non_existent_watch)

    code = check_config(cfg_file)
    assert code == 1

    captured = capsys.readouterr()
    assert "[OK] YAML syntax and schema valid" in captured.out
    assert "[FAIL] Watch directory does not exist" in captured.err


def test_check_config_watch_directory_is_file(tmp_path, capsys):
    cfg_file = tmp_path / "config.yaml"
    file_watch = tmp_path / "not_a_dir"
    file_watch.write_text("hello", encoding="utf-8")
    _write_config(cfg_file, file_watch)

    code = check_config(cfg_file)
    assert code == 1

    captured = capsys.readouterr()
    assert "[FAIL] Watch path is not a directory" in captured.err


def test_check_config_backend_failure(tmp_path, capsys):
    cfg_file = tmp_path / "config.yaml"
    watch_dir = tmp_path / "bags"
    watch_dir.mkdir()
    _write_config(cfg_file, watch_dir)

    fake_registry = MagicMock()
    failing_backend = FakeBackend(should_fail=True)
    fake_registry.get.return_value = failing_backend

    code = check_config(cfg_file, registry=fake_registry)
    assert code == 1

    captured = capsys.readouterr()
    assert "[OK] YAML syntax and schema valid" in captured.out
    assert "[OK] Watch directory exists and is readable" in captured.out
    assert "[FAIL] Storage backend check failed" in captured.err
    assert "Cannot reach remote storage" in captured.err


def test_check_config_success(tmp_path, capsys):
    cfg_file = tmp_path / "config.yaml"
    watch_dir = tmp_path / "bags"
    watch_dir.mkdir()
    _write_config(cfg_file, watch_dir)

    fake_registry = MagicMock()
    working_backend = FakeBackend(should_fail=False)
    fake_registry.get.return_value = working_backend

    code = check_config(cfg_file, registry=fake_registry)
    assert code == 0
    assert working_backend.checked == ["freefox-check"]

    captured = capsys.readouterr()
    assert "[OK] YAML syntax and schema valid" in captured.out
    assert "[OK] Watch directory exists and is readable" in captured.out
    assert "[OK] Storage backend 'rsync' reachable" in captured.out
    assert "Configuration check passed." in captured.out


def test_cli_check_config_flag_invokes_check(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    watch_dir = tmp_path / "bags"
    watch_dir.mkdir()
    _write_config(cfg_file, watch_dir)

    working_backend = FakeBackend(should_fail=False)

    monkeypatch.setattr(
        "freefox.service.BackendRegistry.get",
        lambda self, backend, destination=None: working_backend,
    )
    monkeypatch.setattr(sys, "argv", ["freefox", "--config", str(cfg_file), "--check-config"])

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert working_backend.checked == ["freefox-check"]
