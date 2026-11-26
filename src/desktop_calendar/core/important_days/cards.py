# coding: utf-8
"""重要日子卡片视图模型：排序、倒数天数、周年与周期进度（纯逻辑）。

不依赖 Qt，也不依赖 i18n：名称 / 重复类型等原始字段原样带出，文案由
UI 层拼装。异常数据按条跳过，不让一条坏数据拖垮整个侧栏卡片区。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from desktop_calendar.utils.logging_setup import get_logger

from .common import REPEAT_ONCE, REPEAT_YEAR
from .normalize import normalize_important_day
from .recurrence import (
    get_anniversary_years,
    get_next_important_day_date,
    get_previous_important_day_date,
)

logger = get_logger()

# 没有下次发生日期的重要日子（如已过期的「仅一次」）统一排在末尾
_NO_NEXT_GROUP = 2
_PAST_GROUP = 1
_UPCOMING_GROUP = 0

_MAX_SKIPPED_WARN = 20


@dataclass(frozen=True)
class ImportantDayCardData:
    """单张侧栏卡片需要的全部展示数据。"""

    important_day: dict
    name: str
    next_date: date | None
    days: int | None  # 距下次天数；已过期的「仅一次」为负数
    past: bool
    ordinal_years: int | None
    pinned: bool
    color: str
    type: str
    repeat_type: str
    progress: float | None  # 0..1，本轮周期已过的比例；无法计算时 None
    enabled: bool = True


def _build_card(mem: dict, today: date) -> ImportantDayCardData:
    next_date = get_next_important_day_date(mem, today, include_base=True, normalized=True)

    days: int | None = None
    past = False
    if next_date is not None:
        days = (next_date - today).days
    elif mem["repeat_type"] == REPEAT_ONCE:
        # 已过期的「仅一次」：当作「已过 N 天」的正数日展示
        try:
            target = date(mem["year"], mem["month"], mem["day"])
        except (KeyError, TypeError, ValueError):
            target = None
        if target is not None and target < today:
            next_date = target
            days = -((today - target).days)
            past = True

    ordinal_years = None
    if next_date is not None and mem["repeat_type"] == REPEAT_YEAR:
        try:
            ordinal_years = get_anniversary_years(mem, next_date, normalized=True)
        except Exception:
            logger.debug("计算重要日子周年失败 name=%r", mem.get("name"), exc_info=True)

    progress = None
    if next_date is not None and not past:
        try:
            previous = get_previous_important_day_date(mem, next_date, normalized=True)
        except Exception:
            previous = None
            logger.debug("计算重要日子上次日期失败 name=%r", mem.get("name"), exc_info=True)
        if previous is not None and previous < next_date:
            cycle = (next_date - previous).days
            if cycle > 0:
                elapsed = (today - previous).days
                progress = min(1.0, max(0.0, elapsed / cycle))

    return ImportantDayCardData(
        important_day=mem,
        name=str(mem.get("name") or ""),
        next_date=next_date,
        days=days,
        past=past,
        ordinal_years=ordinal_years,
        pinned=bool(mem.get("pinned", False)),
        color=str(mem.get("color") or ""),
        type=str(mem.get("type") or "solar"),
        repeat_type=str(mem.get("repeat_type") or REPEAT_YEAR),
        progress=progress,
        enabled=bool(mem.get("enabled", True)),
    )


def _sort_key(card: ImportantDayCardData) -> tuple:
    pinned_rank = 0 if card.pinned else 1
    if card.days is None:
        return (pinned_rank, _NO_NEXT_GROUP, 0)
    if card.days >= 0:
        return (pinned_rank, _UPCOMING_GROUP, card.days)
    # 已过期：越近越靠前
    return (pinned_rank, _PAST_GROUP, -card.days)


def build_important_day_cards(
    important_days, today: date | None = None, *, limit: int | None = None
):
    """把配置里的 important_days 转成排好序的卡片列表。

    只保留 ``enabled`` 的条目；``pinned`` 的卡片排在最前，其余按「未来
    最近的在前 → 已过的最近的在中间 → 无下次的在最后」排序。
    ``limit`` 只截断返回结果，不改变排序。
    """
    base = today if today is not None else date.today()
    cards: list[ImportantDayCardData] = []
    skipped = 0

    if not isinstance(important_days, (list, tuple)):
        return []

    for raw in important_days:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        try:
            mem = normalize_important_day(raw)
        except Exception:
            skipped += 1
            logger.debug("重要日子卡片归一化失败: %r", raw, exc_info=True)
            continue
        if not mem.get("enabled", True):
            continue
        try:
            cards.append(_build_card(mem, base))
        except Exception:
            skipped += 1
            logger.debug("重要日子卡片计算失败: %r", raw, exc_info=True)

    cards.sort(key=_sort_key)
    if skipped:
        logger.info("重要日子卡片：跳过 %d 条无法解析的数据", skipped)
        if skipped > _MAX_SKIPPED_WARN:
            logger.warning("重要日子卡片跳过数据过多（%d 条），请检查 important_days", skipped)
    if limit is not None and limit >= 0:
        return cards[:limit]
    return cards
