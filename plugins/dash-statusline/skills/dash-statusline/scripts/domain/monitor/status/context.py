from dataclasses import dataclass


@dataclass
class ContextData:
    # ── 스냅샷 계열: 직전 응답 1회의 usage (context_window.current_usage.*) ──
    # 이론 근거: docs/guides/컨텍스트와-캐싱/ 01(용어)·02(수식)·04(구분)
    read_tokens: int       # cache_read_input_tokens — 캐시된 prefix (~0.1×)
    creation_tokens: int   # cache_creation_input_tokens — 직전 답변+이번 입력 (write 프리미엄)
    uncached_tokens: int   # input_tokens — 캐시 경계 잔여(자투리). "이번 턴 프롬프트"가 아님
    output_tokens: int     # output_tokens — 이번 턴 생성분
    pct: int               # used_percentage — 스냅샷 3합(output 제외) ÷ window
    context_window_size: int  # 0이면 (x/x) 표시 생략
    # ── 누적 계열: cost-tracker 합산. window와 비교·합산 금지 ──
    cost: float            # cost.total_cost_usd — 세션 누적 $
    duration_ms: int       # cost.total_duration_ms
    # ── 기타 ──
    model_id: str          # model.id — 턴 비용(pricing) 계산용
