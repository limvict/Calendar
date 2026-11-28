# coding: utf-8
"""日历单元格展示规则：QDate + 重要日子索引 + 网络节假日 → CellData。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from PyQt6.QtCore import QDate

from desktop_calendar.config.constants import (
    FESTIVAL_NAME_MAP,
    LUNAR_FESTIVALS,
    MONTH_CN,
    NUM_CN_MAP,
    RED_TEXT_SET,
    SOLAR_FESTIVALS,
)
from desktop_calendar.config.i18n import tr
from desktop_calendar.core import lunar as lunar_mod
from desktop_calendar.core.important_days import build_important_day_index
from desktop_calendar.core.lunar import (
    get_lunar_by_datetime,
    is_workday,
    qdate_to_pydate,
)
from desktop_calendar.utils.coerce import to_holiday_kind
from desktop_calendar.utils.logging_setup import get_logger

logger = get_logger()

CELL_NORMAL = "normal"
CELL_IMPORTANT_DAY = "important_day"
CELL_RED = "red"

UNSET = object()
_REPORTED_ERROR_MAX = 2000

__all__ = [
    "CellData",
    "CellPresenter",
    "CELL_NORMAL",
    "CELL_IMPORTANT_DAY",
    "CELL_RED",
    "UNSET",
]


@dataclass(frozen=True)
class CellData:
    lunar_text: str
    kind: str
    is_weekend_work: bool
    is_legal_hol: bool
    has_schedule: bool = False
    schedule_color: str | None = None
    # 命中的重要日子是否农历：日历格用不同颜色区分公历 / 农历重要日子
    important_day_is_lunar: bool = False


class CellPresenter:
    def __init__(self):
        self._important_day_index = build_important_day_index([])
        self._net: dict[str, str] = {}
        self._schedule_markers: dict[str, str] = {}
        self._reported_error_dates = set()

    def set_important_day_list(self, important_day_list) -> None:
        self._important_day_index = build_important_day_index(important_day_list)

    def set_net_holiday(self, data) -> None:
        if not isinstance(data, dict):
            self._net = {}
            return
        normalized: dict[str, str] = {}
        for k, v in data.items():
            if not isinstance(k, str):
                continue
            kind = to_holiday_kind(v)
            if kind is not None:
                normalized[k] = kind
        self._net = normalized

    def set_schedule_dates(self, dates) -> None:
        self.set_schedule_markers({value: "" for value in dates if isinstance(value, str)})

    def set_schedule_markers(self, markers) -> None:
        if not isinstance(markers, dict):
            self._schedule_markers = {}
            return
        self._schedule_markers = {
            day: color
            for day, color in markers.items()
            if isinstance(day, str) and (color is None or isinstance(color, str))
        }

    @property
    def net_count(self) -> int:
        return len(self._net)

    def warmup_for_years(self, years) -> None:
        if not lunar_mod.HAS_CNLUNAR:
            return
        try:
            lunar_mod.warmup_lunar_index_async(years)
        except Exception:
            logger.debug("农历索引预热失败 years=%r", years, exc_info=True)

    def compute(self, qdate: QDate) -> CellData:
        date_str = qdate.toString("yyyy-MM-dd")
        try:
            lunar = self._get_lunar(qdate)
            legal_raw = self._first_legal_holiday_raw(lunar)
            important_day_item = self._first_important_day_item(qdate, lunar)
            lunar_text, kind = self._lunar_text_and_kind(
                qdate, lunar=lunar, legal_raw=legal_raw, important_day_item=important_day_item
            )
            return CellData(
                lunar_text=lunar_text,
                kind=kind,
                is_weekend_work=self._is_weekend_workday(qdate, date_str=date_str),
                is_legal_hol=self._is_legal_holiday(
                    qdate, lunar=lunar, legal_raw=legal_raw, date_str=date_str
                ),
                has_schedule=date_str in self._schedule_markers,
                schedule_color=self._schedule_markers.get(date_str),
                important_day_is_lunar=(
                    kind == CELL_IMPORTANT_DAY
                    and isinstance(important_day_item, dict)
                    and important_day_item.get("type") == "lunar"
                ),
            )
        except Exception:
            if self._should_report(date_str):
                logger.debug(f"CellPresenter.compute 异常 date={date_str}", exc_info=True)
            return CellData("", CELL_NORMAL, False, False)

    def important_day_items_for(self, qdate: QDate) -> list[dict]:
        items = list(self._iter_solar_important_days(qdate))
        if lunar_mod.HAS_CNLUNAR:
            items.extend(self._iter_lunar_important_days(qdate, self._get_lunar(qdate)))
        return items

    # 兼容旧接口：返回命中的重要日子名称列表
    def important_days_for(self, qdate):
        return [
            mem.get("name") or tr("important_day.default_name")
            for mem in self.important_day_items_for(qdate)
        ]

    def _get_lunar(self, qdate: QDate):
        if not lunar_mod.HAS_CNLUNAR:
            return None
        try:
            return get_lunar_by_datetime((qdate.year(), qdate.month(), qdate.day()))
        except Exception:
            return None

    @staticmethod
    def _first_legal_holiday_raw(lunar) -> str | None:
        if lunar is None:
            return None
        try:
            f_list = lunar.get_legalHolidays()
        except Exception:
            return None
        if not f_list:
            return None
        raw = f_list[0] if isinstance(f_list, (list, tuple)) else f_list
        if not raw or raw == "无":
            return None
        return raw

    def _iter_solar_important_days(self, qdate: QDate) -> Iterator[dict]:
        idx = self._important_day_index
        for bucket, key in (
            ("solar_year", (qdate.month(), qdate.day())),
            ("once", (qdate.year(), qdate.month(), qdate.day())),
            ("solar_week", qdate.dayOfWeek()),
            ("solar_month", qdate.day()),
        ):
            yield from idx[bucket].get(key, ())
        # 月末收敛：配置 day 超过本月天数时在今天也展示
        last = qdate.daysInMonth()
        if qdate.day() == last:
            for d in range(last + 1, 32):
                yield from idx["solar_month"].get(d, ())
                yield from idx["solar_year"].get((qdate.month(), d), ())

    def _iter_lunar_important_days(self, qdate: QDate, lunar) -> Iterator[dict]:
        if lunar is None:
            return
        lm = getattr(lunar, "lunarMonth", 0)
        ld = getattr(lunar, "lunarDay", 0)
        leap = bool(getattr(lunar, "isLunarLeapMonth", False))
        idx = self._important_day_index
        for bucket, key in (
            ("lunar_year", (lm, ld, leap)),
            ("lunar_month", (ld, leap)),
        ):
            yield from idx[bucket].get(key, ())
        # 月末收敛：下一天是初一即今天为月末
        if ld < 30:
            nxt = self._get_lunar(qdate.addDays(1))
            if nxt is not None and getattr(nxt, "lunarDay", None) == 1:
                yield from idx["lunar_month"].get((30, leap), ())
                yield from idx["lunar_year"].get((lm, 30, leap), ())

    def _first_important_day_item(self, qdate: QDate, lunar) -> dict | None:
        for m in self._iter_solar_important_days(qdate):
            return m
        if lunar is not None:
            for m in self._iter_lunar_important_days(qdate, lunar):
                return m
        return None

    def _resolve_after_important_day(
        self,
        qdate,
        lunar,
        legal_raw: str | None,
    ) -> tuple[str, str]:
        lm = getattr(lunar, "lunarMonth", 0)
        ld = getattr(lunar, "lunarDay", 0)
        leap = bool(getattr(lunar, "isLunarLeapMonth", False))

        if lunar_mod.is_new_year_eve(lunar, qdate_to_pydate(qdate)):
            return "除夕", CELL_RED
        if legal_raw is not None:
            name = FESTIVAL_NAME_MAP.get(legal_raw, legal_raw)
            return name, (CELL_RED if name in RED_TEXT_SET else CELL_NORMAL)
        if not leap and (lm, ld) in LUNAR_FESTIVALS:
            name = LUNAR_FESTIVALS[(lm, ld)]
            return name, (CELL_RED if name in RED_TEXT_SET else CELL_NORMAL)
        if (qdate.month(), qdate.day()) in SOLAR_FESTIVALS:
            return SOLAR_FESTIVALS[(qdate.month(), qdate.day())], CELL_NORMAL
        term = getattr(lunar, "todaySolarTerms", "")
        if isinstance(term, list) and term:
            term = term[0]
        if term and term != "无":
            return term, CELL_NORMAL
        if ld == 1:
            prefix = tr("cell.leap_prefix") if leap else ""
            return f"{prefix}{MONTH_CN[lm]}", CELL_NORMAL
        return NUM_CN_MAP.get(str(ld), str(ld)), CELL_NORMAL

    def _lunar_text_and_kind(
        self,
        qdate,
        lunar,
        legal_raw=UNSET,
        important_day_item=UNSET,
    ) -> tuple[str, str]:
        try:
            if important_day_item is UNSET:
                important_day_item = self._first_important_day_item(qdate, lunar)
            if important_day_item is not None:
                name = important_day_item.get("name") or tr("important_day.default_name")
                return name, CELL_IMPORTANT_DAY
            if lunar is None:
                return self._solar_festival_fallback(qdate)
            if legal_raw is UNSET:
                legal_raw = self._first_legal_holiday_raw(lunar)
            return self._resolve_after_important_day(qdate, lunar, legal_raw)
        except Exception:
            key = f"ltk:{qdate.toString('yyyy-MM-dd')}"
            if self._should_report(key):
                logger.debug(
                    f"CellPresenter._lunar_text_and_kind 异常 date={qdate.toString('yyyy-MM-dd')}",
                    exc_info=True,
                )
            return "", CELL_NORMAL

    @staticmethod
    def _solar_festival_fallback(qdate) -> tuple[str, str]:
        s = SOLAR_FESTIVALS.get((qdate.month(), qdate.day()))
        return (s, CELL_NORMAL) if s else ("", CELL_NORMAL)

    def _is_weekend_workday(self, qdate, date_str=None) -> bool:
        try:
            if qdate.dayOfWeek() not in (6, 7):
                return False
            key = date_str or qdate.toString("yyyy-MM-dd")
            if key in self._net:
                return self._net[key] == "workday"
            if lunar_mod.HAS_CHINESE_CAL:
                return is_workday(qdate_to_pydate(qdate))
            return False
        except Exception:
            return False

    def _is_legal_holiday(self, qdate, lunar=None, legal_raw=UNSET, date_str=None) -> bool:
        key = date_str or qdate.toString("yyyy-MM-dd")
        if key in self._net:
            return self._net[key] == "holiday"
        if not lunar_mod.HAS_CNLUNAR:
            return False
        if legal_raw is UNSET:
            if lunar is None:
                lunar = self._get_lunar(qdate)
            legal_raw = self._first_legal_holiday_raw(lunar)
        return legal_raw is not None

    def _should_report(self, key: str) -> bool:
        if key in self._reported_error_dates:
            return False
        if len(self._reported_error_dates) >= _REPORTED_ERROR_MAX:
            logger.warning("CellPresenter 异常上报去重表已达上限，已清空")
            self._reported_error_dates.clear()
        self._reported_error_dates.add(key)
        return True
