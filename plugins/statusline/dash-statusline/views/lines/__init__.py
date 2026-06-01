from views.lines.style import default as style
from views.lines.lines import line1, line2, line3, line4, line5


def assemble(context, lang, model, path, git, tools, report) -> str:
    lines = [
        line1.compose(context),
        line2.compose(model, lang),
        line3.compose(path, git),
        line4.compose(tools, style),
    ]
    if report:
        lines.append(line5.compose(report, style))
    return '\n'.join(lines)
