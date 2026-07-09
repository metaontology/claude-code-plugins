from domain.monitor.status.context import ContextData


def _fmt_k(n: int) -> str:
    # 토큰 수를 "19k" / "1m" 단위 문자열로 변환 (1000 미만은 그대로)
    if n < 1000:
        return str(n)
    if n >= 1_000_000:
        v = round(n / 1_000_000)
        return f'{v}m'
    return f'{round(n / 1000)}k'


def _fmt_duration(duration_ms: int) -> str:
    # 경과 시간을 "0m 3s" 형식으로 변환. 60분 이상이면 "1h 2m 3s"로 시간 단위 포함
    total_secs = duration_ms // 1000
    mins, secs = divmod(total_secs, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f'{hours}h {mins}m {secs}s'
    return f'{mins}m {secs}s'


def parse(raw: dict) -> ContextData:
    cw = raw.get('context_window') or {}
    cost = raw.get('cost') or {}
    cu = cw.get('current_usage') or {}  # cache_read_input_tokens은 current_usage 하위
    # 새 세션 첫 호출 시 used_percentage/total_duration_ms 등이 null로 올 수 있음.
    # .get(key, 0) 대신 or 0 사용 — None도 0으로 대체.
    return ContextData(
        pct=int(cw.get('used_percentage') or 0),
        duration_ms=int(cost.get('total_duration_ms') or 0),
        cost=float(cost.get('total_cost_usd') or 0.0),
        input_tokens=int(cw.get('total_input_tokens') or 0),
        output_tokens=int(cw.get('total_output_tokens') or 0),
        cache_read_tokens=int(cu.get('cache_read_input_tokens') or 0),
        context_window_size=int(cw.get('context_window_size') or 0),
    )


def render(data: ContextData, palette, style) -> str:
    filled = round(data.pct / 100 * style.bar_total)
    empty = style.bar_total - filled
    if data.pct >= 90:
        bar_color = palette.crit
    elif data.pct >= 70:
        bar_color = palette.warn
    else:
        bar_color = palette.ok
    bar = bar_color + style.bar_char * filled + palette.dim + style.bar_char * empty + palette.reset

    # "in 19k out 81k cache 19k total 120k/1m" 섹션 구성
    # total = input + output + cache_read (세 분류 합산)
    total = data.input_tokens + data.output_tokens + data.cache_read_tokens
    total_str = f'{bar_color}{_fmt_k(total)}{palette.reset}'
    if data.context_window_size > 0:
        total_str += f'/{_fmt_k(data.context_window_size)}'
    tok = (f'{palette.dim}in{palette.reset} {_fmt_k(data.input_tokens)}'
           f' {palette.dim}out{palette.reset} {_fmt_k(data.output_tokens)}'
           f' {palette.dim}cache{palette.reset} {_fmt_k(data.cache_read_tokens)}'
           f' {palette.dim}total{palette.reset} {total_str}')
    token_section = f' | {tok}'

    return (
        f'🧩 {bar} {data.pct}%'
        f'{token_section}'
        f' | {palette.orange}${data.cost:.2f}{palette.reset}'
        f' | 🕒 {_fmt_duration(data.duration_ms)}'
    )
