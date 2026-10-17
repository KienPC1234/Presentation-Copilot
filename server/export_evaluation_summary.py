"""Export only allowlisted metrics from private expert/conversation reports."""
import argparse
import json
from pathlib import Path


def summarize(report):
    expert = "answers" in report
    rows = report["answers" if expert else "results"]
    if not rows:
        raise ValueError("Empty evaluation report")
    public = {key: report[key] for key in (
        "scope", "model", "answer_model", "review_model", "style", "workers",
        "evidence_sha256", "suite", "runs", "elapsed_seconds",
        "all_requests_p95_seconds", "percentile_method", "semantic_acceptance",
    ) if key in report}
    summaries = []
    for row in rows:
        answer = row.get("answer")
        if not isinstance(answer, dict) and not row.get("error"):
            raise ValueError("Missing answer or execution error")
        failed = bool(row.get("error") or (answer or {}).get("error"))
        item = {key: row[key] for key in ("run", "role", "session", "case", "seconds") if key in row}
        # Error messages, candidate text, review traces and history stay private.
        item["is_error"] = failed
        item["review_status"] = (answer or {}).get("review_status")
        summaries.append(item)
    blocked = sum(row["is_error"] for row in summaries)
    if expert:
        expected = {"valid_answers": len(rows) - blocked, "blocked_or_failed_answers": blocked,
                    "execution_gate_passed": blocked == 0}
        for key, value in expected.items():
            if report.get(key) != value:
                raise ValueError(f"Inconsistent {key}")
        public.update(expected)
    else:
        checks = report["checks"]
        if any(type(check.get("passed")) is not bool for check in checks):
            raise ValueError("Invalid context check")
        public["checks"] = [{"check": check["check"], "passed": check["passed"]} for check in checks]
        passed = bool(checks) and all(check["passed"] for check in checks) and blocked == 0
        if report.get("execution_passed") != passed:
            raise ValueError("Inconsistent execution_passed")
        public["execution_passed"] = passed
    public["answers" if expert else "results"] = summaries
    public["export_schema"] = 1
    return public


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Keep the private report; output must be a different file")
    result = summarize(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
