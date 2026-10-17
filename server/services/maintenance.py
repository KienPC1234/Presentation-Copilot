"""On-demand and startup cleanup of runtime junk, stale exports and logs."""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _summarize(path: Path) -> dict[str, Any]:
    files = 0
    total = 0
    if path.is_dir():
        for root, _dirs, names in os.walk(path):
            for name in names:
                try:
                    total += (Path(root) / name).stat().st_size
                    files += 1
                except OSError:
                    continue
    return {"path": str(path), "files": files, "bytes": total}


def cleanup_runtime(settings) -> dict[str, Any]:
    """Delete leftover temporary audio files from interrupted runs.

    The ChromaDB "index write pending" marker is deliberately preserved: it is
    a recovery signal, not garbage.
    """
    tmp_dir = Path(settings.tmp_dir)
    removed = 0
    freed = 0
    if tmp_dir.is_dir():
        for entry in tmp_dir.iterdir():
            try:
                if entry.is_file():
                    freed += entry.stat().st_size
                    entry.unlink()
                    removed += 1
            except OSError:
                continue
    return {"target": "runtime", "removed": removed, "bytes_freed": freed, "path": str(tmp_dir)}


def _older_than(path: Path, retention_days: int) -> bool:
    cutoff = time.time() - retention_days * 86400
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


def cleanup_exports(export_dir: str, retention_days: int) -> dict[str, Any]:
    """Remove export bundles older than ``retention_days``.

    ``retention_days <= 0`` disables age-based deletion; use the admin panel's
    explicit purge action to remove everything.
    """
    root = Path(export_dir)
    if retention_days <= 0 or not root.is_dir():
        return {"target": "exports", "removed": 0, "bytes_freed": 0, "path": str(root)}

    removed = 0
    freed = 0
    for entry in root.iterdir():
        if entry.is_dir() and _older_than(entry, retention_days):
            freed += _summarize(entry)["bytes"]
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return {"target": "exports", "removed": removed, "bytes_freed": freed, "path": str(root)}


def purge_exports(export_dir: str) -> dict[str, Any]:
    """Delete every generated document bundle. Requires explicit confirmation upstream."""
    root = Path(export_dir)
    if not root.is_dir():
        return {"target": "exports-purge", "removed": 0, "bytes_freed": 0, "path": str(root)}
    freed = _summarize(root)["bytes"]
    removed = 0
    for entry in root.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
            removed += 1
        except OSError:
            continue
    return {"target": "exports-purge", "removed": removed, "bytes_freed": freed, "path": str(root)}


def cleanup_logs(data_dir: str, retention_days: int) -> dict[str, Any]:
    """Remove ``*.log`` files under the data directory older than the retention window."""
    root = Path(data_dir)
    removed = 0
    freed = 0
    if root.is_dir():
        for log_file in root.rglob("*.log"):
            try:
                if retention_days <= 0 or _older_than(log_file, retention_days):
                    freed += log_file.stat().st_size
                    log_file.unlink()
                    removed += 1
            except OSError:
                continue
    return {"target": "logs", "removed": removed, "bytes_freed": freed, "path": str(root)}


def storage_report(settings) -> dict[str, Any]:
    """Sizes of the folders the panel manages, for the maintenance screen."""
    return {
        "data": _summarize(Path(settings.data_dir)),
        "exports": _summarize(Path(settings.export_dir)),
        "tmp": _summarize(Path(settings.tmp_dir)),
        "chroma": _summarize(Path(settings.chroma_persist_dir)),
    }
