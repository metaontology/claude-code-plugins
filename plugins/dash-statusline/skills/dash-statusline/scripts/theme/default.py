from theme.base import ColorPalette

default = ColorPalette(
    ok='\033[32m',
    warn='\033[38;5;228m',
    crit='\033[31m',
    dim='\033[38;5;245m',
    accent='\033[96m',
    highlight='\033[38;5;228m',
    orange='\033[33m',
    orange_soft='\033[38;5;179m',  # 2줄 $ 전용 — 1줄 orange(33)보다 얕은 노랑(tan/gold)
    turn_label='\033[38;2;177;185;249m',  # 2줄 Prev/In/Out 라벨 — periwinkle #B1B9F9
    blue='\033[38;5;75m',
    purple_red='\033[38;5;161m',
    effort='\033[38;5;151m',
    thinking='\033[38;5;193m',
    telemetry='\033[38;2;162;216;247m',  # #A2D8F7
    reset='\033[0m',
)
