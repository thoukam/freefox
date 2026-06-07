"""Outils d'integrite des fichiers."""

from __future__ import annotations

from pathlib import Path

from blake3 import blake3

def calculate_blake3(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Calcule le BLAKE3 d'un fichier sans le charger entierement en RAM."""
    hasher = blake3()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
