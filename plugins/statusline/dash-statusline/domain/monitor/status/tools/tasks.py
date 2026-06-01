from dataclasses import dataclass, field


@dataclass
class TasksItemData:
    todos: list = field(default_factory=list)
