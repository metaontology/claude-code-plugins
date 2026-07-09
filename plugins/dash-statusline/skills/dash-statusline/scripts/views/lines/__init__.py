from views.lines.style import default as style
from views.lines.lines import line1, line2, line3, line4, line5


def assemble(context, lang, model, effort, thinking, path, git, tools, report, telemetry='') -> str:
    lines = [
        line1.compose(context),
        line2.compose(model, effort, thinking, lang, telemetry),
        line3.compose(path, git),
        line4.compose(tools, style),
    ]
    if report:
        lines.append(line5.compose(report, style))
    return '\n'.join(lines)
