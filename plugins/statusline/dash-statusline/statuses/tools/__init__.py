from domain.monitor.status.tools import ToolsData
from domain.monitor.status.tools.events import (
    ToolsEventUse,
    ToolsEventResult,
    ToolsEventTurnBoundary,
)
from statuses.tools._reader import read_events
from statuses.tools.tool import ToolParser
from statuses.tools.agent import AgentParser
from statuses.tools.mcp import McpParser
from statuses.tools.skill import SkillParser
from statuses.tools.tasks import TasksParser


def parse(path, cwd='') -> ToolsData:
    tool_p = ToolParser()
    agent_p = AgentParser(path, cwd)
    mcp_p = McpParser()
    skill_p = SkillParser()
    tasks_p = TasksParser()
    parsers = {
        'tool': tool_p,
        'agent': agent_p,
        'mcp': mcp_p,
        'skill': skill_p,
        'todo': tasks_p,
    }
    reset_keys = ('tool', 'agent', 'mcp', 'skill')
    tid_owner = {}  # tid → parser: ToolsEventResult가 어느 파서 소유인지 추적
    for ev in read_events(path):
        if isinstance(ev, ToolsEventTurnBoundary):
            for k in reset_keys:
                parsers[k].reset()
        elif isinstance(ev, ToolsEventUse):
            p = parsers.get(ev.kind)
            if p:
                p.on_use(ev)
                tid_owner[ev.tid] = p
        elif isinstance(ev, ToolsEventResult):
            p = tid_owner.pop(ev.tid, None)
            if p:
                p.on_result(ev)
    return ToolsData(
        tool=tool_p.result(),
        agent=agent_p.result(),
        mcp=mcp_p.result(),
        skill=skill_p.result(),
        tasks=tasks_p.result(),
    )


def render(data: ToolsData, palette, style) -> str:
    tool_p = ToolParser()
    agent_p = AgentParser()
    mcp_p = McpParser()
    skill_p = SkillParser()
    tasks_p = TasksParser()
    parts = [
        tool_p.render_summary(data.tool, palette, style),
        agent_p.render_summary(data.agent, palette, style),
        mcp_p.render_summary(data.mcp, palette, style),
        skill_p.render_summary(data.skill, palette, style),
        tasks_p.render(data.tasks, palette, style),
    ]
    return ' | '.join(parts)
