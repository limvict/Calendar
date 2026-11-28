# coding: utf-8
from unittest.mock import MagicMock

from desktop_calendar.ui.info_panel import (
    InfoParts,
    _as_list,
    build_info_parts,
    placeholder_key,
    render_html,
)


class TestAsList:
    def test_none(self):
        assert _as_list(None) == []

    def test_wu_string(self):
        assert _as_list("无") == []

    def test_list_filters_wu(self):
        assert _as_list(["a", "无", "b"]) == ["a", "b"]

    def test_tuple_filters_wu(self):
        assert _as_list(("a", "无", "b")) == ["a", "b"]

    def test_single(self):
        assert _as_list("节日") == ["节日"]


class TestPlaceholderKey:
    def test_no_lib(self):
        assert placeholder_key(InfoParts(lunar_lib_available=False)) == "info.no_cnlunar"

    def test_no_data(self):
        assert (
            placeholder_key(InfoParts(lunar_lib_available=True, has_lunar_data=False))
            == "info.lunar_unavailable"
        )

    def test_has_data(self):
        assert (
            placeholder_key(InfoParts(lunar_lib_available=True, has_lunar_data=True))
            == "info.no_events"
        )


class TestRenderHtml:
    def test_lunar_only(self):
        result = render_html(InfoParts(lunar_str="甲辰龙年 正月初一"))
        assert result is not None
        assert "甲辰龙年" in result

    def test_escapes_html(self):
        result = render_html(InfoParts(lunar_str="<script>"))
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_no_important_days_countdown_in_info_line(self):
        # 重要日子倒数已移到侧栏卡片，信息栏不再渲染「重要日子 / 重要日子」片段
        result = render_html(
            InfoParts(lunar_str="甲辰龙年 正月初一", legal_holiday_names=("元旦",))
        )
        assert "重要日子" not in result
        assert "重要日子" not in result

    def test_no_new_year_countdown(self):
        # 春节倒数也移出信息栏，InfoParts 不再带 new_year 字段
        result = render_html(InfoParts(lunar_str="甲辰龙年 正月初一"))
        assert "春节" not in result
        assert "new_year_days" not in vars(InfoParts())


class TestBuildInfoParts:
    def test_none_lunar(self):
        parts = build_info_parts(None, False)
        assert parts.lunar_lib_available is False
        assert parts.has_lunar_data is False

    def test_mock_lunar_extraction(self):
        lunar = MagicMock()
        lunar.lunarMonthCn = "大正月"
        lunar.lunarDayCn = "初一"
        lunar.lunarYearCn = "甲辰"
        lunar.chineseYearZodiac = "龙"
        lunar.todaySolarTerms = "无"
        lunar.get_legalHolidays.return_value = ["元旦节"]
        lunar.get_otherHolidays.return_value = []

        # lunarMonthCn 中的 "大" 会被去掉
        # get_legalHolidays 返回的 "元旦节" 会被 FESTIVAL_NAME_MAP 映射为 "元旦"
        parts = build_info_parts(lunar, True)

        assert parts.lunar_str == "甲辰【龙】 正月初一"
        assert parts.legal_holiday_names == ("元旦",)
