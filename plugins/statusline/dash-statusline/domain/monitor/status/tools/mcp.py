from dataclasses import dataclass, field


@dataclass
class McpItemData:
    running: list = field(default_factory=list)
    done: list = field(default_factory=list)
