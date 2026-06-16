from dataclasses import dataclass


@dataclass
class ThinkingData:
    """Claude의 extended thinking 활성화 상태.

    enabled=True : 이 세션/요청에서 extended thinking이 켜져 있음
    enabled=False or None : 비활성화 또는 정보 없음
    """
    enabled: bool | None
