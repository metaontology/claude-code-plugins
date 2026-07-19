from domain.monitor.status.context import ContextData
from statuses.context import pricing


def _fmt_tok(n: int) -> str:
    # 1000 미만은 그대로, k/m 단위는 소수 1자리(정수면 .0 생략) — "0.4k", "394.6k", "12k", "1m"
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        s = f'{n / 1000:.1f}'
        return (s[:-2] if s.endswith('.0') else s) + 'k'
    s = f'{n / 1_000_000:.1f}'
    return (s[:-2] if s.endswith('.0') else s) + 'm'


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
    cu = cw.get('current_usage') or {}
    model = raw.get('model') or {}
    # 새 세션 첫 호출 시 null이 올 수 있음 — or 0으로 방어 (기존 방침 유지)
    return ContextData(
        read_tokens=int(cu.get('cache_read_input_tokens') or 0),
        creation_tokens=int(cu.get('cache_creation_input_tokens') or 0),
        uncached_tokens=int(cu.get('input_tokens') or 0),
        output_tokens=int(cu.get('output_tokens') or 0),
        pct=int(cw.get('used_percentage') or 0),
        context_window_size=int(cw.get('context_window_size') or 0),
        cost=float(cost.get('total_cost_usd') or 0.0),
        duration_ms=int(cost.get('total_duration_ms') or 0),
        model_id=str(model.get('id') or ''),
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

    # 대괄호 = 바 %의 분자·분모 그대로 (스냅샷 3합/window, output 제외 — Tₙ).
    # 누적 계열을 window와 비교하지 않는다 (옛 total 1m/1m 버그의 원인).
    snapshot = data.read_tokens + data.creation_tokens + data.uncached_tokens
    bracket = ''
    if data.context_window_size > 0:
        bracket = f' [{bar_color}{_fmt_tok(snapshot)}{palette.reset}/{_fmt_tok(data.context_window_size)}]'

    return (
        f'🧩 {bar} {data.pct}%{bracket}'
        f' | {palette.orange}${data.cost:.2f}{palette.reset}'
        f' | 🕒 {_fmt_duration(data.duration_ms)}'
    )


def render_turn(data: ContextData, palette, style) -> str:
    # 직전 턴 스냅샷 라인. 토큰 수 = usage 실측(추정 없음), $ = pricing 참고치(5m 가정).
    # prev(4합) = 직전 응답 직후 현재 컨텍스트 총량(Tₙ₊₁) — 세션 누적($, 1줄)과 다른 계열.
    # 1줄 괄호(3합)와는 output만큼 차이(정상).
    prev_total = data.read_tokens + data.creation_tokens + data.uncached_tokens + data.output_tokens

    cost = pricing.turn_cost(data)
    in_cost = out_cost = total_cost = ''
    if cost is not None:
        in_usd, out_usd = cost
        in_cost = f' {palette.orange_soft}(${in_usd:.2f}){palette.reset}'
        out_cost = f' {palette.orange_soft}(${out_usd:.2f}){palette.reset}'
        total_cost = f' {palette.orange_soft}(${in_usd + out_usd:.2f}){palette.reset}'

    line = (
        f'🗃️ 🇵🇷🇪🇻 {_fmt_tok(prev_total)}{total_cost}'
        f' | 📥 🇮🇳 {palette.dim}read{palette.reset} {_fmt_tok(data.read_tokens)}'
        f' {palette.dim}creation{palette.reset} {_fmt_tok(data.creation_tokens)}'
        f' {palette.dim}uncached{palette.reset} {_fmt_tok(data.uncached_tokens)}{in_cost}'
        f' | 📤 🇴🇺🇹 {_fmt_tok(data.output_tokens)}{out_cost}'
    )

    # cache-cold: rd==0 && cr>0 (11 §4 관찰 구현).
    # - 세션/resume 첫 턴엔 항상 뜸 — 정상(첫 턴은 무조건 cold, 10 §2)
    # - 캐싱 오프(rd=0,cr=0)에선 안 뜸 — cr>0 조건
    # - 부분 cold(모델 왕복, 09 §5)는 미탐지 — v1 범위
    if data.read_tokens == 0 and data.creation_tokens > 0:
        line += ' | 🥶 cache-cold'
    return line
