from dataclasses import dataclass, field

from domain.monitor.status.tools.tool import ToolItemData
from domain.monitor.status.tools.agent import AgentItemData
from domain.monitor.status.tools.mcp import McpItemData
from domain.monitor.status.tools.skill import SkillItemData
from domain.monitor.status.tools.tasks import TasksItemData


@dataclass
class ToolsData:
    tool: ToolItemData = field(default_factory=ToolItemData)
    agent: AgentItemData = field(default_factory=AgentItemData)
    mcp: McpItemData = field(default_factory=McpItemData)
    skill: SkillItemData = field(default_factory=SkillItemData)
    tasks: TasksItemData = field(default_factory=TasksItemData)
