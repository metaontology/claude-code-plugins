from theme.base import ColorPalette
from theme.default import default as _default

_THEMES = {'default': _default}


def load_theme(name: str = 'default') -> ColorPalette:
    return _THEMES.get(name, _default)
