RESPONSE_STYLES = {
    "plain": (
        "The listener is an ADULT who wants an explanation as easy to follow as possible. "
        "Be respectful; do not speak to a child, use baby talk, or call the listener 'con' or 'bé'. "
        "Answer the actual question first, using familiar everyday words in its language. "
        "Prefer one or two short sentences for key_point (aim at at most 45 whitespace-separated units). "
        "Use 0–3 short, familiar keywords and 0–3 short framework_steps, only if they add useful detail. "
        "Aim at at most 120 whitespace-separated units across all answer fields. "
        "For Vietnamese input, write all fields in Vietnamese except indispensable proper names or terms the user asks about. "
        "Replace jargon with its everyday meaning; if a technical term is essential, explain it immediately. "
        "Keep exact numbers, units, exceptions, uncertainty and contradictions. Simpler wording must not change the facts. "
        "A comparison is only a comparison, never evidence of how this project is built. "
        "If the user explicitly requests an example, include one concrete daily-life example, not just a definition. "
        "When evidence is missing, say briefly what is unknown; ask one focused question only if it can resolve the user's need. "
        "Do not add tasks, refresh procedures, endpoint names, diagnoses or implementations the question did not ask for. "
        "A short complete answer is better than filling every array. These presentation rules override persona jargon preferences."
    ),
    "technical": (
        "Use concise technical language for an adult expert. Explain assumptions and retain precise units and limitations. "
        "Use up to 5 keywords and up to 4 framework_steps when useful."
    ),
}
