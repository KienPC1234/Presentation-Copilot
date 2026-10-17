"""Document types the AI can render to markdown. Dependency-free for reuse."""

DOCUMENT_KINDS: tuple[str, ...] = ("qa", "rebuttal", "evidence", "outline", "cheatsheet")

KIND_LABELS: dict[str, str] = {
    "qa": "Defense Q&A + preparation checklist",
    "rebuttal": "Rebuttal / counter-argument script",
    "evidence": "Evidence + citation appendix",
    "outline": "Slide / presentation outline",
    "cheatsheet": "One-page cheat sheet",
}

LANGUAGES: tuple[str, ...] = ("vi", "en")
