"""ISO 8601 타임스탬프 파싱 및 로컬 시간 포맷 유틸."""
from datetime import datetime


def parse_iso(ts: str) -> datetime:
    """ISO 8601 문자열을 timezone-aware datetime으로 변환. 'Z' suffix 처리 포함."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def fmt_local(dt: datetime) -> str:
    """datetime을 로컬 시간대 기준 'YYYY-MM-DD HH:MM:SS' 문자열로 변환."""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def fmt_local_short(dt: datetime) -> str:
    """datetime을 로컬 시간대 기준 'YYYY-MM-DD HH:MM' 문자열로 변환."""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")
