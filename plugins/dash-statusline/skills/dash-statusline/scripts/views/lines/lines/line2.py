def compose(model: str, effort: str, thinking: str, lang: str, telemetry: str = '') -> str:
    parts = [model] + [p for p in [effort, thinking, lang, telemetry] if p]
    return ' | '.join(parts)
