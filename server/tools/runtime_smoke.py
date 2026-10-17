"""Opt-in integration smoke using synthetic documents and configured Ollama.

Run from server/: python runtime_smoke.py --model gpt-oss:120b-cloud
Cloud models receive only the synthetic fixture in this script.
"""

import sys
from pathlib import Path as _Path

# Allow running from server/tools/ by putting the server package root on the path.
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import argparse
import json
import tempfile
import time
from pathlib import Path

from config import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", default="runtime-smoke.json")
    parser.add_argument("--embedding-url", help="Optional isolated Ollama embedding server")
    args = parser.parse_args()
    settings.ollama_model = args.model
    # Import after selecting the configured model.
    from services.agent_service import AgentService
    from services.context_manager import SessionContext
    from services.rag_service import RAGService

    report = {"model": args.model, "fixture": "synthetic", "checks": [], "answers": []}
    with tempfile.TemporaryDirectory(prefix="copilot-runtime-") as root:
        root = Path(root)
        settings.chroma_persist_dir = str(root / "vectors")
        docs = root / "docs"
        docs.mkdir()
        fixture = docs / "harbor.md"
        fixture.write_text(
            "Project Harbor synthetic test specification.\n"
            "API access tokens expire after exactly 17 minutes.\n"
            "The queue retains events for 9 days.\n"
            "There is no throughput benchmark, GPU benchmark or latency measurement in this document.\n",
            encoding="utf-8")
        if args.embedding_url:
            settings.ollama_embedding_base_url = args.embedding_url
        rag = RAGService()
        rag.ingest_documents(str(docs))
        count = rag.get_stats()["total_chunks"]
        rag.ingest_documents(str(docs))
        assert rag.get_stats()["total_chunks"] == count, "Repeated ingest duplicated chunks"
        report["checks"].append("repeated_ingest_no_duplicates")
        chunks = rag.query("How long do Harbor access tokens last?")
        assert chunks and any("17 minutes" in item for item in chunks), "Fixture was not retrieved"
        report["checks"].append("real_ollama_embeddings_and_chroma_retrieval")

        agent = AgentService(rag)
        agent.set_persona("custom", "You are a factual assistant. Preserve literal braces: {project}.")
        report["checks"].append("persona_with_literal_braces")
        agent.set_persona("general")
        questions = [
            "For Project Harbor, how long do access tokens last and how long are queue events retained?",
            "What is Project Harbor's measured throughput in requests per second?",
            "Dự án Harbor có thời hạn access token bao lâu? Trả lời bằng tiếng Việt.",
        ]
        for index, question in enumerate(questions):
            started = time.perf_counter()
            result = agent.run(question, SessionContext(f"runtime-{index}"))
            report["answers"].append({"question": question, "result": result,
                                      "elapsed_seconds": round(time.perf_counter() - started, 2)})
            # These are contract checks, not semantic accuracy assertions.
            if result.get("error"):
                report["checks"].append(f"agent_case_{index}_ERROR")
            else:
                assert "[harbor.md]" in result.get("retrieved_sources", [])
                report["checks"].append(f"agent_case_{index}_valid_schema_and_provenance")
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if any(answer["result"].get("error") for answer in report["answers"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
