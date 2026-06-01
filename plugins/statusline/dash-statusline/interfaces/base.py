from typing import Protocol, Any


class BasePalette(Protocol):
    ok: str
    warn: str
    crit: str
    dim: str
    accent: str
    highlight: str
    orange: str
    reset: str


class BaseStatus(Protocol):
    def parse(self, raw: dict) -> Any: ...
    def render(self, data: Any, palette: BasePalette, style: Any) -> str: ...


class BaseView(Protocol):
    def assemble(self, **rendered: str) -> str: ...
