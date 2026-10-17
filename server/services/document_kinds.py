"""Document types the AI can render to markdown. Dependency-free for reuse."""

DOCUMENT_KINDS: tuple[str, ...] = ("qa", "rebuttal", "outline", "cheatsheet", "rehearsal", "evidence")

KIND_LABELS: dict[str, str] = {
    "qa": "Defense Q&A + preparation checklist",
    "rebuttal": "Rebuttal / counter-argument script",
    "outline": "Slide / presentation outline",
    "cheatsheet": "One-page cheat sheet",
    "rehearsal": "Rehearsal plan & risky-claim list",
    "evidence": "Evidence + citation appendix",
}

LANGUAGES: tuple[str, ...] = ("vi", "en")
