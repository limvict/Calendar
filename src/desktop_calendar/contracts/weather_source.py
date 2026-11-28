from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherInfo:
    city: str
    temperature: float  # ℃
    code: int  # WMO 天气代码
    description: str  # 中文描述
    humidity: int | None = None
    wind_speed: float | None = None
    updated_at: str = ""
