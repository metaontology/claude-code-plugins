from domain.monitor.status.model import ModelData
from domain.monitor.status.tools import ToolsData
from statuses.tools.tool import ToolParser
from statuses.tools.agent import AgentParser
from statuses.tools.mcp import McpParser
from statuses.tools.skill import SkillParser

_MODE_MAP = {
    'plan': 'plan mode',
    'bypassPermissions': 'bypass mode',
    'default': 'edit mode',
    '': 'edit mode',
}


def render(data: ToolsData, palette, style, model_data: ModelData = None) -> str:
    tool_p = ToolParser()
    agent_p = AgentParser()
    mcp_p = McpParser()
    skill_p = SkillParser()
    PT2 = '\U0001d495 '
    segments = []
    td = tool_p.render_detail(data.tool, palette, style)
    if td:
        segments.append(td)
    ad = agent_p.render_detail(data.agent, palette, style)
    if ad:
        segments.append(ad)
    md = mcp_p.render_detail(data.mcp, palette, style)
    if md:
        segments.append(md)
    sd = skill_p.render_detail(data.skill, palette, style)
    if sd:
        segments.append(sd)
    in_progress = [t for t in data.tasks.todos if t.get('status') == 'in_progress']
    if in_progress:
        content = in_progress[0].get('content', '')
        display = content[:50] + ('...' if len(content) > 50 else '')
        segments.append(f'{PT2}{palette.warn}{display}{palette.reset}')

    bell_content = ' '.join(segments)

    mode_label = _MODE_MAP.get(
        model_data.permission_mode if model_data else '', 'edit mode'
    )
    model_short = model_data.display_name_short if model_data else ''
    mode_part = f'▶▶ {mode_label} ⌬  {model_short}' if model_short else f'▶▶ {mode_label}'
    suffix = f'  {palette.dim}{mode_part}{palette.reset}'

    if bell_content:
        return f'🔔 {bell_content}{suffix}'
    return ''
