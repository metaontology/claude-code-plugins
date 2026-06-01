from views import lines as _lines

_VIEWS = {'lines': _lines}


def select_view(name: str = 'lines'):
    return _VIEWS.get(name, _lines)
