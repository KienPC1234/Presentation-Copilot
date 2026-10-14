"""Standalone CLI script to ingest project documents and codebase into ChromaDB.

Usage:
    python ingest.py
    python ingest.py --path "C:/path/to/my/project"
    python ingest.py --docs-dir ./data/docs
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from config import settings  # noqa: E402
from services.rag_service import RAGService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest project documents & codebase into ChromaDB vector store."
    )
    parser.add_argument(
        "--path",
        "--docs-dir",
        dest="target_path",
        default=settings.docs_dir,
        help=f"Path to project repository or documents folder (default: {settings.docs_dir})",
    )
    args = parser.parse_args()

    target_path = Path(args.target_path)
    print("=" * 60)
    print(" PRESENTATION COPILOT | KNOWLEDGE INGESTION")
    print("=" * 60)
    print(f"Target Path     : {target_path.resolve()}")
    print(f"ChromaDB Store  : {Path(settings.chroma_persist_dir).resolve()}")
    print()

    rag = RAGService()
    verify_res = rag.verify_path(str(target_path))
    if not verify_res["valid"]:
        print(f"[ERROR] {verify_res['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Path verified. Found {verify_res['total_files']} candidate files.")
    if verify_res["sample_files"]:
        print(f"Samples: {', '.join(verify_res['sample_files'])}")
    print()

    print("[ingest] Embedding documents via nomic-embed-text ...")
    start = time.perf_counter()
    try:
        result = rag.ingest_documents(str(target_path))
    except Exception as exc:
        print(f"[ERROR] Ingestion failed: {exc}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.perf_counter() - start
    print()
    print(f"[ingest] Finished in {elapsed:.1f}s")
    print(f"[ingest] Chunks ingested : {result.get('chunks_ingested', 0)}")
    print(f"[ingest] Files indexed   : {result.get('files_indexed', 0)}")
    print(f"[ingest] Vector database is ready for live queries.")
    print("=" * 60)


if __name__ == "__main__":
    main()
