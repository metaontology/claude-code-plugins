from dataclasses import dataclass

from interfaces.base import BasePalette


@dataclass
class ColorPalette:
    ok: str
    warn: str
    crit: str
    dim: str
    accent: str
    highlight: str
    orange: str
    blue: str
    purple_red: str
    reset: str


def _check() -> None:
    _: BasePalette = ColorPalette.__new__(ColorPalette)  # type: ignore
