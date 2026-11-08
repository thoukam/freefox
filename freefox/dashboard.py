"""Dashboard web local pour suivre les uploads FreeFox."""

from __future__ import annotations

import argparse
import importlib.resources
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from freefox.config import CollectorConfig
from freefox.queue import QueueEntry, UploadQueue

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO = _ASSETS / "freefox.png"


def _load_dashboard_html() -> str:
    try:
        ref = importlib.resources.files("freefox").joinpath("assets", "dashboard.html")
        return ref.read_text(encoding="utf-8")
    except Exception:
        path = _ASSETS / "dashboard.html"
        return path.read_text(encoding="utf-8")


HTML = _load_dashboard_html()


def _human_error(error: str | None) -> str:
    if not error:
        return ""
    lowered = error.lower()
    if (
        "quota google drive depasse" in lowered
        or "storagequotaexceeded" in lowered
        or "storage quota" in lowered
    ):
        return "L'espace Google Drive du compte est plein."
    if (
        "erreur reseau temporaire" in lowered
        or "temporary failure in name resolution" in lowered
        or "nameresolutionerror" in lowered
        or "failed to resolve" in lowered
        or "read timed out" in lowered
        or "connection timed out" in lowered
        or "max retries exceeded" in lowered
    ):
        return "Connexion instable vers Google Drive. FreeFox reessaiera automatiquement."
    if "local file missing" in lowered or "file not found" in lowered:
        return "Le fichier local est introuvable ou a ete deplace."
    if "resumable upload session expired" in lowered:
        return "La session d'upload Google Drive a expire. FreeFox va recreer une session."
    if "integrity metadata mismatch" in lowered or "local file size changed" in lowered:
        return "Controle d'integrite echoue. Le fichier est considere comme incoherent."
    if "permission" in lowered or "403" in lowered:
        return "Google Drive refuse l'operation. Verifiez les droits du compte ou du dossier."
    return "Erreur d'upload. Consultez les logs FreeFox pour le detail technique."


def _integrity_status(entry: QueueEntry) -> tuple[str, str]:
    error = (entry.error or "").lower()
    if "integrity metadata mismatch" in error or "local file size changed" in error:
        return "NO", "integrity-no"
    if entry.status.value == "done" and entry.blake3_digest:
        return "OK", "integrity-ok"
    if entry.blake3_digest:
        return "attente", "integrity-pending"
    return "—", "integrity-off"


def _entry_to_dict(entry: QueueEntry) -> dict:
    now = time.time()
    progress = max(0.0, min(100.0, entry.progress_percent or 0.0))
    started_at = entry.upload_started_at or 0.0
    finished_at = entry.upload_finished_at or 0.0
    bytes_sent = getattr(entry, "uploaded_bytes", None) or (
        int(entry.size_bytes * (progress / 100.0)) if started_at else 0
    )
    end_time = finished_at or (now if started_at else 0.0)
    duration = max(0.0, end_time - started_at) if started_at else 0.0
    bps = (
        (entry.size_bytes / duration if entry.status.value == "done" else bytes_sent / duration)
        if started_at and duration > 0
        else 0.0
    )
    remaining = max(0, entry.size_bytes - bytes_sent)
    eta = remaining / bps if entry.status.value == "uploading" and bps > 0 else 0.0
    retry_after = max(0.0, entry.next_retry_at - now) if entry.status.value == "queued" else 0.0
    integrity_status, integrity_status_class = _integrity_status(entry)
    return {
        "id": entry.id,
        "local_path": entry.local_path,
        "remote_path": entry.remote_path,
        "status": entry.status.value,
        "retries": entry.retries,
        "next_retry_at": entry.next_retry_at,
        "retry_after_seconds": retry_after,
        "created_at": entry.created_at,
        "updated_at": getattr(entry, "updated_at", entry.created_at),
        "upload_started_at": entry.upload_started_at,
        "upload_finished_at": entry.upload_finished_at,
        "size_bytes": entry.size_bytes,
        "progress_percent": progress,
        "bytes_sent_estimate": bytes_sent,
        "bytes_per_second": bps,
        "duration_seconds": duration,
        "eta_seconds": eta,
        "blake3_digest": entry.blake3_digest,
        "integrity_status": integrity_status,
        "integrity_status_class": integrity_status_class,
        "error": entry.error,
        "error_summary": _human_error(entry.error),
    }


def _metrics(entries):
    ds = [_entry_to_dict(e) for e in entries]
    return {
        "bytes_sent_estimate": float(sum(d["bytes_sent_estimate"] for d in ds)),
        "active_bytes_per_second": float(
            sum(d["bytes_per_second"] for d in ds if d["status"] == "uploading")
        ),
    }


def _list_watch_files(config, entries):
    directory = config.watch.directory
    queued = {e.local_path for e in entries}
    now = time.time()
    if not directory.exists():
        return []
    files = []
    exts = {x.lower() for x in config.watch.extensions}
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        is_q = str(path) in queued
        age = max(0.0, now - stat.st_mtime)
        if is_q:
            state, sc, ri = "queued", "queued", "—"
        elif age < config.watch.stable_seconds:
            state, sc, ri = "writing", "writing", f"{config.watch.stable_seconds - age:.1f}s"
        else:
            state, sc, ri = "not queued", "not-queued", "now"
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
                "state": state,
                "state_class": sc,
                "ready_in": ri,
            }
        )
    files.sort(key=lambda r: r["modified_at"], reverse=True)
    return files[:100]


def _incidents(config, entries):
    out = []
    if not config.watch.directory.exists():
        out.append(
            {"kind": "dossier surveille", "message": f"N'existe pas: {config.watch.directory}"}
        )
    if not config.drive.credentials_file.exists():
        out.append(
            {
                "kind": "identifiants",
                "message": f"Fichier manquant: {config.drive.credentials_file}",
            }
        )
    for e in entries:
        error = e.error or ""
        if e.status.value != "done" and (
            "Quota Google Drive depasse" in error
            or "storageQuotaExceeded" in error
            or "storage quota" in error.lower()
        ):
            out.append(
                {
                    "kind": "quota Google Drive",
                    "message": (
                        "L'espace Drive du compte est plein. "
                        "FreeFox reessaiera automatiquement quand de l'espace sera disponible."
                    ),
                }
            )
            continue
        if e.status.value != "done" and (
            "Erreur reseau temporaire" in error
            or "temporary failure in name resolution" in error.lower()
            or "read timed out" in error.lower()
            or "connection timed out" in error.lower()
            or "failed to resolve" in error.lower()
        ):
            out.append(
                {
                    "kind": "reseau temporaire",
                    "message": (
                        "La connexion vers Google Drive est instable. "
                        "FreeFox reessaiera automatiquement."
                    ),
                }
            )
            continue
        if e.status.value == "failed":
            out.append(
                {
                    "kind": f"transfert en echec #{e.id}",
                    "message": _human_error(e.error) or e.remote_path,
                }
            )
    unq = [f for f in _list_watch_files(config, entries) if f["state"] == "not queued"]
    if unq:
        out.append(
            {
                "kind": "surveillance",
                "message": f"{len(unq)} bag(s) stable(s) non ajoute(s) a la file. Le service tourne-t-il ?",
            }
        )
    return out[:20]


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, addr, config):
        super().__init__(addr, DashboardHandler)
        self.config_obj = config
        self.queue = UploadQueue(config.queue_db)
        self.started_at = time.time()


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, *_):
        return

    def _send(self, code, ct, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode())
            return
        if p == "/brand/freefox.png":
            try:
                self._send(200, "image/png", _LOGO.read_bytes())
            except OSError:
                self._send(404, "text/plain", b"introuvable")
            return
        if p == "/api/status":
            qs = parse_qs(urlparse(self.path).query)
            lim = int(qs.get("limit", ["100"])[0])
            entries = self.server.queue.recent(limit=lim)
            cfg = self.server.config_obj
            body = json.dumps(
                {
                    "config": {
                        "robot_id": cfg.robot_id,
                        "watch_directory": str(cfg.watch.directory),
                        "storage_backend": cfg.storage.backend,
                        "queue_db": str(cfg.queue_db),
                        "drive_folder_id": cfg.drive.target_folder_id,
                        "rsync_destination": cfg.rsync.destination,
                        "extensions": cfg.watch.extensions,
                        "stable_seconds": cfg.watch.stable_seconds,
                    },
                    "stats": self.server.queue.stats(),
                    "queued": self.server.queue.queued_breakdown(),
                    "metrics": _metrics(entries),
                    "entries": [_entry_to_dict(e) for e in entries],
                    "files": _list_watch_files(cfg, entries),
                    "incidents": _incidents(cfg, entries),
                },
                indent=2,
            ).encode()
            self._send(200, "application/json", body)
            return
        self._send(404, "text/plain", b"introuvable")


def main():
    parser = argparse.ArgumentParser(description="Dashboard web local FreeFox")
    parser.add_argument("-c", "--config", default="/etc/freefox/config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    config = CollectorConfig.from_yaml(args.config)
    server = DashboardServer((args.host, args.port), config)
    url = f"http://{args.host}:{args.port}"
    print(f"Dashboard FreeFox -> {url}")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
