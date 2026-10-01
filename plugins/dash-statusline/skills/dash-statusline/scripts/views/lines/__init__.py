from views.lines.style import default as style
from views.lines.lines import line1, line_turn, line2, line3, line_session, line4, line5


def assemble(context, turn, lang, model, effort, thinking, path, git, tools, report, telemetry='',
             session='Ⓜ️ ...') -> str:
    lines = [
        line1.compose(context),
        line_turn.compose(turn),
        line2.compose(model, effort, thinking, lang, telemetry),
        line3.compose(path, git),
        line_session.compose(session),
        line4.compose(tools, style),
    ]
    if report:
        lines.append(line5.compose(report, style))
    return '\n'.join(lines)
