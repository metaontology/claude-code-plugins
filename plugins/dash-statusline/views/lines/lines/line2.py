def compose(model: str, effort: str, thinking: str, lang: str) -> str:
    parts = [model] + [p for p in [effort, thinking, lang] if p]
    return ' | '.join(parts)
