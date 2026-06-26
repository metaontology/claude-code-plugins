from dataclasses import dataclass, field


@dataclass
class ToolItemData:
    running: list = field(default_factory=list)
    done: list = field(default_factory=list)
