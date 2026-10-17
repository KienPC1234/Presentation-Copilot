"""Remove curator instructions from the original PRIVATE FPTE test fixture.

Preserves all original source excerpts byte-for-byte. Does not read the live
project, infer undocumented technology choices, or publish project source.
"""
import argparse
import hashlib
import json
from pathlib import Path

ORIGINAL_SHA256 = "57e76e74853a5b818db75c54e20357f7a8954a7e61d9297d4b9cd40db3d9a253"
HEADER = """# FPTEELiterature source excerpts — evidence fixture v2

Scope: selected source excerpts only. Other project files and actual runtime behavior are not established by this fixture. No benchmark is included with these excerpts.

## Neutral English reading guide, translated from the source lines below
index.html:7,67 describes multi-subject learning materials and practice exams for students, teachers and schools.
index.html:125 says leaving the exam screen/tab, losing focus/fullscreen and copy/paste are signals for teacher review; these signals do not automatically deduct scores.
api.php:85-104 computes deadline from started_at + max(1, duration) * 60 and the minimum with a valid ends_at. It returns remaining=max(0, deadline-now).
api.php:388-425 includes access checks, draft saving, a submission_status call to saved_submission_result with user, exam and key, and the beginning of submit_exam. The body of saved_submission_result and the final result persistence are not included here.

## Original source excerpts, unchanged

"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Keep the original fixture; output must be a different file")
    original = args.input.read_bytes()
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("Unexpected original fixture revision")
    text = original.decode("utf-8")
    body = text[text.index("## index.html:7-7"):]
    corrected = (HEADER + body).encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(corrected)
    receipt = {"original_fixture_sha256": ORIGINAL_SHA256,
               "neutral_fixture_sha256": hashlib.sha256(corrected).hexdigest(),
               "unchanged_source_excerpt_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
               "change": "Curator instructions and unsupported negative technology framing removed; all original code/HTML excerpts preserved."}
    args.output.with_suffix(".provenance.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
