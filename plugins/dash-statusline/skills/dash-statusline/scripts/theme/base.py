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
    orange_soft: str  # 2줄 턴 라인 $ 전용 — orange보다 얕은 노랑(222)
    blue: str
    purple_red: str
    effort: str
    thinking: str
    telemetry: str
    reset: str


def _check() -> None:
    _: BasePalette = ColorPalette.__new__(ColorPalette)  # type: ignore
