from dataclasses import dataclass


@dataclass
class LinesStyle:
    bar_char: str
    bar_total: int
    indent: str


default = LinesStyle(
    bar_char='█',
    bar_total=13,
    indent='   ',
)
