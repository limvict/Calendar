# coding: utf-8
"""重要日子：归一化、日期匹配、下次发生日期计算、日历索引与侧栏卡片模型。

按职责拆成五个模块：

- `common`    ：重复类型常量与日期/整数小工具
- `normalize` ：把外部数据收敛成合法结构
- `recurrence`：公历/农历的匹配与「下一次发生」计算
- `index`     ：按「公历/农历 × 年/月/周」建表，供日历快速查询
- `cards`     ：侧栏倒数日卡片的排序与进度（纯数据，不含文案）

`from desktop_calendar.core.important_days import ...` 是统一导入入口。
"""

from __future__ import annotations

from .cards import ImportantDayCardData, build_important_day_cards
from .common import REPEAT_MONTH, REPEAT_ONCE, REPEAT_WEEK, REPEAT_YEAR
from .index import build_important_day_index
from .normalize import normalize_important_day, normalize_important_days
from .recurrence import (
    get_anniversary_years,
    get_next_important_day_date,
    get_previous_important_day_date,
    match_important_day_date,
)

__all__ = [
    "REPEAT_YEAR",
    "REPEAT_MONTH",
    "REPEAT_WEEK",
    "normalize_important_day",
    "normalize_important_days",
    "get_next_important_day_date",
    "get_previous_important_day_date",
    "match_important_day_date",
    "get_anniversary_years",
    "build_important_day_index",
    "build_important_day_cards",
    "ImportantDayCardData",
    "REPEAT_ONCE",
]
