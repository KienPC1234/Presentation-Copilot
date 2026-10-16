"""Narrow completeness checks; these do not verify factual accuracy."""
import re


def missing_requested_example(question: str, answer: dict) -> bool:
    if re.search(r"(?:không cần|đừng|không muốn).{0,20}ví dụ|(?:no|without).{0,12}(?:example|analogy)", question, re.I):
        return False
    if not re.search(r"ví dụ|\bexample\b|\banalogy\b", question, re.I):
        return False
    text = " ".join([answer["key_point"], *answer.get("framework_steps", [])])
    return not re.search(r"ví dụ|chẳng hạn|tưởng tượng|for example|for instance|imagine|\bgiống\b|\bnhư\b|\blike\b", text, re.I)
