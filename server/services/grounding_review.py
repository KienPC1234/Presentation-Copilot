"""Structured coverage and verbatim-support review; entailment remains model judged."""
import json
import re
from decimal import Decimal, InvalidOperation

from langchain_core.messages import HumanMessage, SystemMessage
from services.output_validation import parse_json_object
from services.answer_review import REVIEW_PROMPT, deterministic_issues, parse_review

STRUCTURED_PROMPT = """
Use this more detailed JSON schema instead of the short issues-only schema:
{"coverage":[{"id":"r1","status":"answered|unknown|missing","fields":["key_point"]}],
 "fields":[{"field":"key_point","spans":[{"text":"exact fragment from candidate field",
            "verdict":"supported|unknown|proposal|general|label|separator|unsupported|contradiction",
            "reason":"short explanation","support":[{"id":"e1","quote":"exact excerpt"}]}]}],
 "issues":[{"code":"...","detail":"..."}]}
Assess EVERY provided requirement ID and EVERY answer field exactly once; use only provided field names.
Coverage may reference a nonempty keywords/framework_steps collection as a whole; field audits still assess every indexed item.
Unknown means the answer explicitly admits the requested fact is not established, not that you skipped the part.
Split EVERY field into ordered, contiguous text spans covering the whole field; copy text exactly, do not paraphrase.
Each span must contain only ONE factual assertion or one contiguous non-factual phrase. Never sample just some clauses.
Split mixed fields into separate factual, proposed and unknown spans. There is no mixed verdict.
For each project fact use supported and quote the provided evidence VERBATIM, not a paraphrase.
Never join non-contiguous code with inserted "..." or "[…]" inside a quote. Use separate exact substrings instead.
Use general ONLY for general knowledge with no project-specific factual assertions; label ONLY for keyword labels.
Unsupported includes factual clauses hidden inside otherwise correct fields. Check ALL clauses, not just the first.
Each supported span must be <=300 characters and requires at least one exact quote; each quote <=500 characters, at most 4 per span.
The quote must support the SAME action/entity/condition as the candidate: never borrow a return field from
a different API action or use draft-saving evidence as proof of final-submission behavior.
Treat absent API bodies or persistence code as unknown. Do not infer atomicity or exclusive ownership from names.
An expected HTTP status/protocol result for a test of an existing API is a factual contract, even inside a proposal.
Do not confuse an invalid identifier's validation error with the outcome for a well-formed identifier owned by another user.
Security tests may propose denial of access/data; exact HTTP codes need evidence under the SAME precondition.
For arithmetic correctly derived from question/tool numbers, use general and explain the derivation briefly.
Explain reasons in <=200 characters per span. Include only materially relevant quotes.
Keyword labels may use label, but a guarantee or policy is a claim, not a label. Do not label other fields as label.
Punctuation-only spans may use separator with no support. Use contradiction for a claim contradicted by the source.
For discourse headings such as "Quy trình xem xét:" use general, not separator or label.
The support array may be omitted for non-factual spans; supported spans always need it.
Reason may be omitted for non-factual spans; supported factual spans need a brief reason and exact support.
If any requested part is not answered or explicitly acknowledged as unknown, its coverage status is missing.
Review the original question too: report missing_part if the supplied requirement list itself omits a requested part.
Keep JSON concise; do not output reasoning traces or additional keys.
"""

FRAMING_LABELS = frozenset({
    "theo đoạn mã", "theo mã", "theo mã nguồn", "theo tài liệu", "hiện có trong mã nguồn",
    "bằng chứng hiện có", "chưa được chứng minh", "chưa chứng minh", "đề xuất", "đề xuất kiểm thử",
    "kết luận", "giới hạn", "according to the code", "proposed test", "known", "unknown",
})


def novel_measurement_issues(question, answer, evidence, tool_facts):
    """Catch invented numeric targets; existence of a number is not entailment."""
    supplied = "\n".join([question, *evidence,
        *(str(t.get("result", "")) for t in tool_facts if t.get("tool") == "calculator")])
    def values(value):
        # This guard must not pretend to resolve locale ambiguity. Accept a
        # plausible grouped-thousands form as well as a decimal form; semantic
        # review still checks meaning, units and actual support.
        result = set()
        candidates = [value.replace(",", ".")]
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
            candidates.append(value.replace(",", "").replace(".", ""))
        for candidate in candidates:
            try:
                result.add(Decimal(candidate).normalize())
            except InvalidOperation:
                pass
        return result
    def normalize_spacing(text):
        return re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))", "", text)
    def numbers(text):
        return set().union(*(values(v) for v in re.findall(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\d.])", normalize_spacing(text))))
    known = numbers(supplied)
    issues = []
    for field, text in answer_fields(answer).items():
        for match in re.finditer(r"(?<!\w)(\d+(?:[.,]\d+)*)\s*(?:milliseconds?|seconds?|minutes?|ms\b|s\b|giây\b|phút\b|%)", normalize_spacing(text), re.I):
            if not values(match.group(1)) & known:
                issues.append({"code": "unsupported_claim", "detail":
                    f"Field {field} introduces numeric target {match.group(0)} not provided by the question/evidence/calculator. Remove arbitrary thresholds; state that acceptance criteria must be agreed and measured."})
    return issues


def answer_fields(answer):
    result = {"key_point": answer["key_point"]}
    for key in ("keywords", "framework_steps"):
        result.update({f"{key}.{i}": value for i, value in enumerate(answer.get(key, []))})
    return result


def parse_grounding_review(raw, answer, requirements, evidence):
    data = parse_json_object(raw, max_chars=48000)
    if set(data) != {"coverage", "fields", "issues"}:
        raise ValueError("Incomplete grounding review")
    issues = parse_review(json.dumps({"issues": data["issues"]}))
    if issues:
        # A valid semantic veto is enough to reject a candidate. Exhaustive
        # spans/quotes are mandatory for approval, not for denying release.
        return issues
    expected_fields = answer_fields(answer)
    expected_parts = {part["id"]: part["request"] for part in requirements}
    if not isinstance(data["coverage"], list) or len(data["coverage"]) != len(expected_parts):
        raise ValueError("Coverage must assess every requested part")
    seen = set()
    for item in data["coverage"]:
        if (not isinstance(item, dict) or set(item) != {"id", "status", "fields"}
                or not isinstance(item["id"], str) or item["id"] not in expected_parts or item["id"] in seen
                or item["status"] not in ("answered", "unknown", "missing")
                or not isinstance(item["fields"], list)
                or any(not isinstance(field, str) or (field not in expected_fields
                       and (field not in ("keywords", "framework_steps")
                            or not any(name.startswith(field + ".") for name in expected_fields))) for field in item["fields"])
                or (item["status"] != "missing" and not item["fields"])):
            raise ValueError("Invalid coverage assessment")
        seen.add(item["id"])
        if item["status"] == "missing":
            issues.append({"code": "missing_part", "detail": f"Missing {item['id']}: {expected_parts[item['id']]}"})
    if not isinstance(data["fields"], list) or len(data["fields"]) != len(expected_fields):
        raise ValueError("Review must assess every answer field")
    seen = set()
    for item in data["fields"]:
        if (not isinstance(item, dict) or set(item) != {"field", "spans"}
                or not isinstance(item["field"], str) or item["field"] not in expected_fields or item["field"] in seen
                or not isinstance(item["spans"], list) or not 1 <= len(item["spans"]) <= 20):
            raise ValueError("Invalid field assessment")
        seen.add(item["field"])
        text = re.sub(r"\s+", " ", expected_fields[item["field"]]).strip()
        cursor = 0
        for span in item["spans"]:
            if (not isinstance(span, dict) or not {"text", "verdict"} <= set(span)
                    or not set(span) <= {"text", "verdict", "reason", "support"}
                    or not isinstance(span["text"], str) or not span["text"].strip()
                    or span["verdict"] not in ("supported", "unknown", "proposal", "general", "label", "separator", "unsupported", "contradiction")
                    or not isinstance(span.get("reason", ""), str) or len(span.get("reason", "")) > 500
                    or (span["verdict"] == "supported" and not span.get("reason", "").strip())
                    or not isinstance(span.get("support", []), list) or len(span.get("support", [])) > 4):
                raise ValueError("Invalid claim span")
            fragment = re.sub(r"\s+", " ", span["text"]).strip()
            start = text.find(fragment, cursor)
            # Separators may be omitted, but no words, numbers or operators.
            if start < 0 or re.search(r"[^\s,;:.()\u2014]", text[cursor:start]):
                raise ValueError("Review omitted or rewrote candidate text")
            cursor = start + len(fragment)
            invalid_support = False
            for support in span.get("support", []):
                if (not isinstance(support, dict) or set(support) != {"id", "quote"}
                        or not isinstance(support["id"], str) or support["id"] not in evidence
                        or not isinstance(support["quote"], str) or not 1 <= len(support["quote"].strip()) <= 500
                        or support["quote"] not in evidence[support["id"]]):
                    invalid_support = True
            punctuation_only = not re.search(r"[^\s,;:.()\u2014]", fragment)
            framing_only = fragment.strip(" ,;:.()\u2014").casefold() in FRAMING_LABELS
            if punctuation_only or framing_only:
                continue  # A separator/discourse heading asserts no project fact.
            if invalid_support:
                raise ValueError(f"Non-verbatim or forged support for {item['field']}; use valid evidence IDs and separate literal substrings without inserted ellipses")
            if span["verdict"] == "supported" and (not span.get("support") or len(fragment) > 300):
                raise ValueError(f"Supported span for {item['field']} needs exact support and one claim of at most 300 characters")
            if (span["verdict"] == "label" and not item["field"].startswith("keywords.")
                    or span["verdict"] == "separator"):
                raise ValueError(f"Substantive text in {item['field']} must be assessed as a fact, unknown, proposal or general statement")
            if span["verdict"] in ("unsupported", "contradiction"):
                issues.append({"code": "unsupported_claim", "detail":
                    f"Field {item['field']}: {span.get('reason', 'Unverified assertion.')} Every factual clause needs a matching source for the same action/condition; split long claims and remove ungrounded claims."})
        if re.search(r"[^\s,;:.()\u2014]", text[cursor:]):
            raise ValueError("Review omitted candidate ending")
    return issues


def review_grounding(llm, question, answer, evidence, tool_facts, requirements, history="", topic=None):
    vetoes = deterministic_issues(question, answer, evidence) + novel_measurement_issues(question, answer, evidence, tool_facts)
    if vetoes:
        return vetoes
    sources = {f"e{i}": chunk for i, chunk in enumerate(dict.fromkeys(evidence), 1)}
    # Arithmetic/web observations stay separate: they are not source code or
    # evidence for how the product behaves.
    messages = [
        SystemMessage(content=REVIEW_PROMPT + "\n" + STRUCTURED_PROMPT),
        HumanMessage(content=json.dumps({"question": question, "presentation_topic": topic,
            "requirements": requirements, "history": history, "candidate": answer,
            "answer_fields": answer_fields(answer), "evidence": sources,
            "tool_observations": tool_facts}, ensure_ascii=False)),
    ]
    response = llm.invoke(messages)
    try:
        reviewed = parse_grounding_review(response.content, answer, requirements, sources)
    except ValueError as exc:
        # Retry malformed review protocol once, never retry a valid negative
        # verdict until it turns positive. The original candidate is unchanged.
        response = llm.invoke([
            SystemMessage(content=REVIEW_PROMPT + "\n" + STRUCTURED_PROMPT
                + f"\nPrevious review protocol was invalid: {exc}. Re-review the ORIGINAL candidate and evidence. "
                  "Use exactly the supplied requirement IDs and answer field names, zero-based indexes; cover all fields and text. "
                  "Return the entire corrected review JSON. Do not alter the candidate or invent fields."),
            messages[-1],
        ])
        reviewed = parse_grounding_review(response.content, answer, requirements, sources)
    return reviewed
