"""Affiche l'etat de la file FreeFox depuis SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from freefox.queue import UploadQueue


def _shorten(value: str, width: int = 52) -> str:
    if len(value) <= width:
        return value
    return "..." + value[-(width - 3):]


def _format_rate(entry) -> str:
    if not entry.upload_started_at:
        return "-"
    end = entry.upload_finished_at or __import__("time").time()
    elapsed = max(0.0, end - entry.upload_started_at)
    if elapsed <= 0:
        return "-"
    sent = entry.size_bytes
    if entry.status.value != "done":
        sent = entry.uploaded_bytes or int(
            entry.size_bytes * (entry.progress_percent / 100.0)
        )
    bps = sent / elapsed
    mib = bps / 1024 / 1024
    mbps = bps * 8 / 1000 / 1000
    return f"{mib:.2f} MiB/s {mbps:.2f} Mbps"


def _format_duration(entry) -> str:
    if not entry.upload_started_at:
        return "-"
    end = entry.upload_finished_at or __import__("time").time()
    seconds = max(0, int(end - entry.upload_started_at))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def main() -> None:
    parser = argparse.ArgumentParser(description="Affiche l'etat de la file d'upload FreeFox.")
    parser.add_argument(
        "db",
        nargs="?",
        default="/var/lib/freefox/queue.db",
        help="Chemin vers queue.db (defaut: /var/lib/freefox/queue.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Nombre de lignes recentes a afficher (defaut: 20)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Base de file introuvable: {db_path}")

    queue = UploadQueue(db_path, initialize=False)
    print(f"Stats: {queue.stats()}")
    print()
    print(
        f"{'ID':>4}  {'STATUT':<9}  {'PROGRES':>8}  {'DUREE':>8}  "
        f"{'DEBIT':>24}  {'ESSAI':>5}  {'SESSION':>7}  DISTANT"
    )
    print("-" * 128)
    for entry in queue.recent(limit=args.limit):
        print(
            f"{entry.id:>4}  "
            f"{entry.status.value:<9}  "
            f"{entry.progress_percent:>7.1f}%  "
            f"{_format_duration(entry):>8}  "
            f"{_format_rate(entry):>24}  "
            f"{entry.retries:>5}  "
            f"{'session' if entry.upload_session_uri else '-':>7}  "
            f"{_shorten(entry.remote_path)}"
        )
        if entry.error:
            print(f"{'':>4}  erreur: {entry.error}")


if __name__ == "__main__":
    main()
