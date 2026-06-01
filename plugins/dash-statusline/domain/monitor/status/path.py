from dataclasses import dataclass


@dataclass
class PathData:
    full: str
    parent: str
    last: str
