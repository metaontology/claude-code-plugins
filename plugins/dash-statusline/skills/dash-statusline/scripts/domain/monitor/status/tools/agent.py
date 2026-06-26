from dataclasses import dataclass, field


@dataclass
class AgentItemData:
    running: list = field(default_factory=list)
    done: list = field(default_factory=list)
