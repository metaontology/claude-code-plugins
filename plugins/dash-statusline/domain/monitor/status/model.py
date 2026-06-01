from dataclasses import dataclass


@dataclass
class ModelData:
    display_name: str        # 원문 그대로 (LINE2용): "Sonnet 4.6 (1M context)"
    display_name_short: str  # 단축명 (LINE5 ▶▶용): "sonnet-4.6[1m]"
    permission_mode: str
