# coding: utf-8
"""重要日子卡片模型：排序、倒数天数、周年、周期进度与新增字段归一化。"""

from datetime import date

import pytest

from desktop_calendar.core import lunar as lunar_mod
from desktop_calendar.core.important_days import (
    build_important_day_cards,
    get_previous_important_day_date,
    normalize_important_day,
)

TODAY = date(2026, 11, 26)


def _mem(**kwargs):
    base = {
        "name": "重要日子",
        "type": "solar",
        "month": 1,
        "day": 1,
        "repeat_type": "year",
        "enabled": True,
        "advance_days": 0,
    }
    base.update(kwargs)
    return base


class TestCardsOrdering:
    def test_only_enabled_items(self):
        cards = build_important_day_cards(
            [_mem(name="开"), _mem(name="关", enabled=False)],
            TODAY,
        )
        assert [card.name for card in cards] == ["开"]

    def test_pinned_first_then_upcoming_then_past(self):
        cards = build_important_day_cards(
            [
                _mem(name="未来", month=12, day=31),
                _mem(name="置顶", month=1, day=1, pinned=True),
                _mem(name="已过", repeat_type="once", year=2020, month=1, day=1),
                _mem(name="最近", month=12, day=1),
            ],
            TODAY,
        )
        assert [card.name for card in cards] == ["置顶", "最近", "未来", "已过"]

    def test_past_once_days_are_negative(self):
        cards = build_important_day_cards(
            [_mem(repeat_type="once", year=2020, month=1, day=1)], TODAY
        )
        assert cards[0].past is True
        assert cards[0].days == -(TODAY - date(2020, 1, 1)).days
        assert cards[0].next_date == date(2020, 1, 1)

    def test_limit_keeps_sorted_prefix(self):
        mems = [_mem(name=f"m{i}", month=i + 1, day=1) for i in range(5)]
        cards = build_important_day_cards(mems, TODAY, limit=2)
        assert len(cards) == 2
        assert cards[0].days <= cards[1].days

    def test_invalid_entries_are_skipped(self):
        cards = build_important_day_cards([None, "x", 3, _mem(name="正常")], TODAY)
        assert [card.name for card in cards] == ["正常"]

    def test_non_list_returns_empty(self):
        assert build_important_day_cards("bad", TODAY) == []
        assert build_important_day_cards(None, TODAY) == []


class TestCardsContent:
    def test_ordinal_years_from_since_year(self):
        cards = build_important_day_cards(
            [_mem(month=4, day=15, since_year=2000)],
            TODAY,
        )
        # 下一次是 2027-04-15，2000 年起算 → 27 周年
        assert cards[0].next_date == date(2027, 4, 15)
        assert cards[0].ordinal_years == 27

    def test_no_ordinal_without_since_year(self):
        cards = build_important_day_cards([_mem(month=4, day=15)], TODAY)
        assert cards[0].ordinal_years is None

    def test_weekly_progress_uses_full_cycle(self):
        # 2026-11-26 是周四；下一次周三 12-02，上次 11-25 → 周期 7 天，已过 1 天
        cards = build_important_day_cards([_mem(repeat_type="week", day=3)], TODAY)
        assert cards[0].next_date == date(2026, 12, 2)
        assert cards[0].progress == pytest.approx(1 / 7)

    def test_yearly_progress_between_occurrences(self):
        cards = build_important_day_cards([_mem(month=12, day=24)], TODAY)
        # 2025-12-24 ~ 2026-12-24（365 天），已过 337 天
        assert cards[0].progress == pytest.approx(337 / 365)

    def test_once_has_no_progress(self):
        cards = build_important_day_cards(
            [_mem(repeat_type="once", year=2027, month=1, day=10)], TODAY
        )
        assert cards[0].progress is None

    def test_pinned_and_color_passed_through(self):
        cards = build_important_day_cards([_mem(pinned=True, color="#5c9ead")], TODAY)
        # normalize 会把颜色统一成大写
        assert cards[0].pinned is True
        assert cards[0].color == "#5C9EAD"


class TestPreviousOccurrence:
    def test_week(self):
        prev = get_previous_important_day_date(_mem(repeat_type="week", day=3), date(2026, 12, 2))
        assert prev == date(2026, 11, 25)

    def test_solar_yearly(self):
        prev = get_previous_important_day_date(_mem(month=4, day=15), date(2026, 4, 15))
        assert prev == date(2025, 4, 15)

    def test_solar_monthly_converges_to_month_end(self):
        prev = get_previous_important_day_date(
            _mem(month=1, day=31, repeat_type="month"), date(2026, 3, 31)
        )
        # 2 月没有 31 号 → 落到 2 月 28 日
        assert prev == date(2026, 2, 28)

    def test_once_has_no_previous(self):
        assert (
            get_previous_important_day_date(
                _mem(repeat_type="once", year=2026, month=5, day=1), date(2026, 5, 1)
            )
            is None
        )

    @pytest.mark.skipif(not lunar_mod.HAS_CNLUNAR, reason="需要 cnlunar")
    def test_lunar_yearly(self):
        prev = get_previous_important_day_date(
            _mem(type="lunar", month=8, day=15), date(2026, 9, 25)
        )
        assert prev == date(2025, 10, 6)


class TestNormalizeCardFields:
    def test_defaults(self):
        mem = normalize_important_day({})
        assert mem["pinned"] is False
        assert mem["color"] == ""

    def test_pinned_coerced(self):
        assert normalize_important_day({"pinned": 1})["pinned"] is True
        assert normalize_important_day({"pinned": "no"})["pinned"] is False

    def test_valid_color_uppercased(self):
        assert normalize_important_day({"color": "#5c9ead"})["color"] == "#5C9EAD"

    @pytest.mark.parametrize("bad", ["red", "#12345", "#GGGGGG", 123, None])
    def test_invalid_color_falls_back_to_empty(self, bad):
        assert normalize_important_day({"color": bad})["color"] == ""
