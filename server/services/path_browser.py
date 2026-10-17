"""Read-only browsing of server-side paths for the remote admin panel.

The panel may only see and select paths inside explicitly configured roots:
the read-only host bind mount (``HOST_MOUNT_ROOT``) plus the bundled docs and
generated-export directories. Symlinks are resolved before the containment
check so a link cannot escape a root.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 500


class PathAccessError(ValueError):
    """Raised when a requested path is not inside any allowed root."""


def _resolve(path: str) -> Path:
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:  # broken symlink loop, etc.
        raise PathAccessError(f"Unusable path: {path}") from exc


def allowed_roots(settings) -> list[dict[str, Any]]:
    """Configured roots the panel may browse, de-duplicated by real path."""
    candidates: list[tuple[str, str]] = []
    if settings.host_mount_root.strip():
        candidates.append((settings.host_mount_root, "Server machine (read-only mount)"))
    candidates.append((settings.docs_dir, "Bundled project documents"))
    candidates.append((settings.export_dir, "Generated markdown documents"))

    roots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw, label in candidates:
        try:
            resolved = _resolve(raw)
        except PathAccessError:
            continue
        key = str(resolved)
        if key in seen or not resolved.is_dir():
            continue
        seen.add(key)
        roots.append({"label": label, "path": key, "writable": os.access(key, os.W_OK)})
    return roots


def resolve_within_roots(path: str, roots: list[dict[str, Any]]) -> Path:
    """Resolve ``path`` and require it to live inside one of ``roots``."""
    candidate = _resolve(path)
    for root in roots:
        root_path = Path(root["path"])
        if candidate == root_path or candidate.is_relative_to(root_path):
            return candidate
    raise PathAccessError("Path is outside the folders this panel may access")


def _entry_info(entry: os.DirEntry[str]) -> dict[str, Any] | None:
    try:
        stat = entry.stat(follow_symlinks=False)
    except OSError:
        return None
    is_dir = entry.is_dir(follow_symlinks=False)
    return {
        "name": entry.name,
        "path": entry.path,
        "type": "dir" if is_dir else "file",
        "size": None if is_dir else stat.st_size,
        "modified": int(stat.st_mtime),
        "readable": os.access(entry.path, os.R_OK),
    }


def list_directory(path: str, roots: list[dict[str, Any]], show_hidden: bool = False,
                   limit: int = _MAX_ENTRIES) -> dict[str, Any]:
    """List a directory inside the allowed roots. Never raises for bad input."""
    try:
        target = resolve_within_roots(path, roots)
    except PathAccessError as exc:
        return {"ok": False, "error": str(exc)}

    if not target.exists():
        return {"ok": False, "error": f"Path does not exist: {target}"}
    if not target.is_dir():
        return {"ok": False, "error": f"Not a directory: {target}"}
    if not os.access(target, os.R_OK | os.X_OK):
        return {"ok": False, "error": f"Permission denied: {target}"}

    entries: list[dict[str, Any]] = []
    try:
        with os.scandir(target) as iterator:
            for entry in iterator:
                if not show_hidden and entry.name.startswith("."):
                    continue
                info = _entry_info(entry)
                if info is not None:
                    entries.append(info)
    except OSError as exc:
        return {"ok": False, "error": f"Could not read directory: {exc.strerror or exc}"}

    entries.sort(key=lambda item: (item["type"] != "dir", item["name"].casefold()))
    truncated = len(entries) > limit
    entries = entries[:limit]

    parent = str(target.parent) if target.parent != target else None
    if parent is not None and not any(
        Path(parent) == Path(root["path"]) or Path(parent).is_relative_to(Path(root["path"]))
        for root in roots
    ):
        parent = None

    return {
        "ok": True,
        "path": str(target),
        "parent": parent,
        "entries": entries,
        "truncated": truncated,
        "matching_root": next((root["label"] for root in roots
                               if target == Path(root["path"]) or target.is_relative_to(Path(root["path"]))), None),
    }
