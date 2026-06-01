from dataclasses import dataclass


@dataclass
class ToolsEventUse:
    tid: str
    name: str
    inp: dict
    ts: float
    kind: str  # 'tool' | 'agent' | 'mcp' | 'skill' | 'todo'


@dataclass
class ToolsEventResult:
    tid: str
    ts: float


@dataclass
class ToolsEventTurnBoundary:
    pass
