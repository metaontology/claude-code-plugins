from dataclasses import dataclass


@dataclass
class RateLimitsData:
    five_hour_pct: int | None
    seven_day_pct: int | None
