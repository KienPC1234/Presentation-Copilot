CATEGORIES = ("product", "technical", "evidence", "risks", "alternatives", "operations")


def validate_plan(data, evidence, count, language="vi"):
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list) or len(data["questions"]) != count:
        raise ValueError("Expected the requested number of questions")
    allowed = {item["id"] for item in evidence}
    questions = []
    seen = set()
    for index, item in enumerate(data["questions"], 1):
        if not isinstance(item, dict) or item.get("category") not in CATEGORIES:
            raise ValueError("Invalid question category")
        cleaned = {"id": f"q{index}", "category": item["category"]}
        for key in ("question", "purpose", "follow_up"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 1000:
                raise ValueError(f"Invalid {key}")
            cleaned[key] = value.strip()
        if cleaned["question"].casefold() in seen:
            raise ValueError("Duplicate question")
        seen.add(cleaned["question"].casefold())
        outline = item.get("answer_outline")
        refs = item.get("evidence_ids")
        if not isinstance(outline, list) or len(outline) > 3 or any(not isinstance(x, str) or not x.strip() or len(x) > 700 for x in outline):
            raise ValueError("Invalid answer outline")
        if not isinstance(refs, list) or any(not isinstance(x, str) or x not in allowed for x in refs):
            raise ValueError("Unknown evidence reference")
        if not refs:
            outline = ["Chưa có bằng chứng trong tài liệu. Chuẩn bị số liệu hoặc ví dụ đã kiểm chứng trước khi trả lời."
                       if language == "vi" else "No evidence supplied. Prepare verified measurements or examples before answering."]
        cleaned.update(answer_outline=outline, evidence_ids=list(dict.fromkeys(refs)),
                       evidence_status="cited" if refs else "missing")
        questions.append(cleaned)
    if count >= 6 and set(q["category"] for q in questions) != set(CATEGORIES):
        raise ValueError("Missing required defense categories")
    return questions
