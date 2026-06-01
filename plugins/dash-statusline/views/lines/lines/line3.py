def compose(path: str, git: str) -> str:
    return path + (' | ' + git if git else '')
