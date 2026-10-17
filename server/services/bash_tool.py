"""Opt-in shell execution for the ReAct agent's ``bash`` tool.

This is **not** a security sandbox. When enabled it can run whatever the server
process itself is allowed to run, and it can read anything that process can
read. It exists so a trusted operator can let the agent inspect and ingest a
project tree without leaving the panel. It is therefore:

* disabled by default (``AGENT_BASH_ENABLED=false``);
* confined to a working directory inside the panel's allowed roots;
* bounded by a timeout, a command-length cap and an output cap;
* screened by a small denylist for obviously destructive commands;
* refused when it would touch an absolute path outside the allowed roots
  (``/dev/null`` and ``/tmp`` are permitted).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from services.path_browser import PathAccessError, allowed_roots, resolve_within_roots

logger = logging.getLogger(__name__)

_MAX_COMMAND_CHARS = 2000

_DENYLIST = (
    re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-?[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(?:\s|$|\*)"),
    re.compile(r"\bmkfs(\.\w+)?\b"),
    re.compile(r"\bdd\s+[^\n]*\bof=/dev/"),
    re.compile(r":\s*\(\s*\)\s*\{"),
    re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bchmod\s+-R?\s*777\s+/(?:\s|$)"),
    re.compile(r"\bchown\s+-R\s+[^\s]+\s+/(?:\s|$)"),
    re.compile(r">\s*/dev/(sd|nvme|mmcblk)"),
    re.compile(r"\bnc\s+-e\b"),
    re.compile(r"\b(curl|wget)\b[^|;\n]*\|\s*(sudo\s+)?(sh|bash|zsh)\b"),
    re.compile(r">\s*/etc/"),
)

_ABSOLUTE_PATH = re.compile(r"(?<![\w./-])(/[A-Za-z0-9_./-]+)")
_URL = re.compile(r"[a-z][a-z0-9+.\-]*://\S+", re.IGNORECASE)
_PATH_ALLOWLIST = ("/dev/null", "/tmp", "/usr", "/bin", "/sbin", "/lib", "/opt/conda")


def _roots(settings) -> list[dict[str, Any]]:
    return allowed_roots(settings)


def _outside_allowed_roots(command: str, roots: list[dict[str, Any]]) -> str | None:
    root_paths = [Path(root["path"]) for root in roots]
    # URLs (e.g. http://host.docker.internal:11434) are not filesystem paths.
    scan = _URL.sub(" ", command)
    for match in _ABSOLUTE_PATH.findall(scan):
        if match.startswith(_PATH_ALLOWLIST):
            continue
        try:
            candidate = Path(match).resolve()
        except (OSError, RuntimeError):
            continue
        if not any(candidate == root or candidate.is_relative_to(root) for root in root_paths):
            return f"Blocked: {match} is outside the folders this agent may touch"
    return None


def _working_directory(settings, requested: str | None) -> Path:
    roots = _roots(settings)
    if not roots:
        raise PathAccessError("No browsable root is configured for the agent")
    if requested and requested.strip():
        return resolve_within_roots(requested.strip(), roots)
    preferred = settings.host_mount_root.strip() or settings.docs_dir
    try:
        return resolve_within_roots(preferred, roots)
    except PathAccessError:
        return Path(roots[0]["path"])


def evaluate(command: str, settings) -> str | None:
    """Return a refusal message, or ``None`` when the command may run."""
    if not isinstance(command, str) or not command.strip():
        return "Empty command."
    if len(command) > _MAX_COMMAND_CHARS:
        return f"Command exceeds {_MAX_COMMAND_CHARS} characters."
    for pattern in _DENYLIST:
        if pattern.search(command):
            return "Refused: this command matches the destructive-command denylist."
    outside = _outside_allowed_roots(command, _roots(settings))
    if outside:
        return outside
    return None


def run(command: str, settings, cwd: str | None = None) -> str:
    """Run ``command`` under the configured bounds and return trimmed output."""
    refusal = evaluate(command, settings)
    if refusal:
        logger.warning("bash tool refused a command: %s", refusal)
        return refusal

    try:
        workdir = _working_directory(settings, cwd)
    except PathAccessError as exc:
        return str(exc)

    timeout = max(1, int(settings.bash_timeout_seconds))
    limit = max(200, int(settings.bash_max_output_chars))

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s."
    except OSError as exc:
        return f"Command could not start: {exc}"

    output = (completed.stdout or "") + (("\n[stderr]\n" + completed.stderr) if completed.stderr else "")
    output = output.strip() or "(no output)"
    if len(output) > limit:
        output = output[:limit] + f"\n…[truncated at {limit} characters]"
    logger.info("bash tool ran in %s (exit=%s)", workdir, completed.returncode)
    return f"exit={completed.returncode}\n{output}"
