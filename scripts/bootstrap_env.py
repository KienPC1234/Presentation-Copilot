"""Create or update server/.env with a generated API_TOKEN.

Run once after cloning, or again with --force to rotate the key. The Docker
entrypoint does the same inside the container, so this script is mainly for
non-Docker or custom deployments.
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
ENV_PATH = SERVER_DIR / ".env"
EXAMPLE_PATH = SERVER_DIR / ".env.example"
TOKEN_LINE = re.compile(r"^API_TOKEN=.*$", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="rotate the key even if one is already set")
    parser.add_argument("--print-only", action="store_true",
                        help="print the existing key without changing anything")
    args = parser.parse_args()

    if not ENV_PATH.exists():
        if not EXAMPLE_PATH.exists():
            print(f"Cannot find {EXAMPLE_PATH}", file=sys.stderr)
            return 1
        ENV_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Created {ENV_PATH} from .env.example")

    text = ENV_PATH.read_text(encoding="utf-8")
    match = TOKEN_LINE.search(text)
    current = match.group(0).split("=", 1)[1].strip() if match else ""

    if args.print_only:
        print(current or "(no token set; loopback-only access)")
        return 0

    if current and not args.force:
        print(f"API_TOKEN already set ({current[:4]}…). Use --force to rotate.")
        return 0

    token = secrets.token_urlsafe(32)
    if match:
        text = TOKEN_LINE.sub(f"API_TOKEN={token}", text, count=1)
    else:
        text = text.rstrip() + f"\n\n# Server settings\nAPI_TOKEN={token}\n"
    ENV_PATH.write_text(text, encoding="utf-8")
    try:
        ENV_PATH.chmod(0o600)
    except OSError:
        pass
    print(f"Wrote a new API_TOKEN to {ENV_PATH}")
    print(f"Set PRESENTATION_COPILOT_API_TOKEN={token} for the Windows client.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
