from dataclasses import dataclass


@dataclass
class ContextData:
    pct: int
    duration_ms: int
    cost: float
    # 토큰 분류: stdin context_window.total_input_tokens / total_output_tokens,
    #   current_usage.cache_read_input_tokens (cache hit 분)
    # render에서 "in 19k out 81k cache 19k total 120k/1m" 형태로 표시
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    context_window_size: int  # 컨텍스트 윈도우 한도 (예: 1m); 0이면 표시 생략
