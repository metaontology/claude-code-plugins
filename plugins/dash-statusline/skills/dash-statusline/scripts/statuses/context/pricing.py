"""직전 턴 비용(참고치) 계산.

[왜 직접 계산하는가 — statusline stdin JSON이 주는 것]
Claude Code가 statusline에 주입하는 JSON(원본 src/components/StatusLine.tsx:83-97)에는
카테고리별 $가 없다. 반면 토큰은 4카테고리로 완전 분해되어 오므로,
technically 4개 카테고리(read/creation/uncached/output) 각각의 $를 여기서 계산할 수 있다.

| stdin 필드                                   | 내용                              | 계열   |
|----------------------------------------------|-----------------------------------|--------|
| cost.total_cost_usd                          | 세션 누적 총액 $ 하나 (분해 없음) | 누적   |
| context_window.total_input_tokens            | uncached만 누적 (read/creation 미포함) | 누적 |
| context_window.total_output_tokens           | output 누적                       | 누적   |
| context_window.current_usage.input_tokens    | 직전 턴 uncached(자투리)          | 스냅샷 |
| context_window.current_usage.output_tokens   | 직전 턴 생성분                    | 스냅샷 |
| context_window.current_usage.cache_creation_input_tokens | 직전 턴 캐시 기록분   | 스냅샷 |
| context_window.current_usage.cache_read_input_tokens     | 직전 턴 캐시 적중분   | 스냅샷 |

누적 read/creation 카운터는 Claude Code 내부에는 있으나 payload에 실리지 않는다
→ 세션 누적 $의 카테고리 분해는 statusline 단독으로는 불가.

[가정]
- cache_creation 배율은 5m TTL(1.25×)로 가정한다. 1h latch(2×) 여부는 요청의
  cache_control 속성이라 클라이언트에서 관찰 불가하고, 코드 기본값(allowlist
  fallback = 빈 목록)이 5m이기 때문. 1h latch 사용자라면 creation 부분만 1.6배
  과소평가된다. 따라서 모든 $는 참고치다.
- 단가는 claude-api 스킬 검증값(2026-07). Sonnet 5는 표준가($3/$15) 사용
  (2026-08-31까지 intro $2/$10 프로모션은 무시 — 참고치이므로 보수적으로).

[범례] read = cache_read, creation = cache_creation, uncached = uncached input(자투리).
uncached는 "이번 턴 user prompt"가 아니라 캐시 경계 처리 잔여분이다
(docs/guides/컨텍스트와-캐싱/01·04 참조).
"""

# $/MTok (input 단가, output 단가) — prefix 매칭 (dated full ID 대응)
PRICES = {
    'claude-fable-5': (10.0, 50.0),
    'claude-mythos-5': (10.0, 50.0),
    'claude-opus-4-8': (5.0, 25.0),
    'claude-opus-4-7': (5.0, 25.0),
    'claude-opus-4-6': (5.0, 25.0),
    'claude-opus-4-5': (5.0, 25.0),
    'claude-sonnet-5': (3.0, 15.0),
    'claude-sonnet-4-6': (3.0, 15.0),
    'claude-sonnet-4-5': (3.0, 15.0),
    'claude-haiku-4-5': (1.0, 5.0),
}

READ_MULT = 0.1       # cache read ≈ 0.1× base input
CREATION_MULT = 1.25  # cache write 5m TTL = 1.25× (1h이면 2× — 관찰 불가, 5m 가정)


def _lookup(model_id: str):
    for key, prices in PRICES.items():
        if model_id.startswith(key):
            return prices
    return None


def turn_cost(data):
    """직전 턴의 (입력측 $, 출력측 $). 모델 미등록이면 None — 표시 생략."""
    prices = _lookup(data.model_id)
    if prices is None:
        return None
    in_price, out_price = prices
    in_usd = (
        data.read_tokens * READ_MULT
        + data.creation_tokens * CREATION_MULT
        + data.uncached_tokens
    ) * in_price / 1_000_000
    out_usd = data.output_tokens * out_price / 1_000_000
    return in_usd, out_usd
