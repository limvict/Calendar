# coding: utf-8
import html
from dataclasses import dataclass
from datetime import date

from desktop_calendar.config.constants import (
    DEFAULT_THEME,
    FESTIVAL_NAME_MAP,
    LUNAR_FESTIVALS,
    RED_TEXT_SET,
)
from desktop_calendar.config.i18n import tr
from desktop_calendar.core import lunar as lunar_mod
from desktop_calendar.ui.theme import ThemeResolver


@dataclass(frozen=True)
class InfoParts:
    lunar_str: str | None = None
    term_text: str | None = None
    has_lunar_data: bool = False
    lunar_lib_available: bool = True
    legal_holiday_names: tuple = ()
    ordinary_holiday_names: tuple = ()


def _as_list(v) -> list[str]:
    if v is None or v == "无":
        return []
    if isinstance(v, (list, tuple)):
        return [x for x in v if x and x != "无"]
    return [v]


def _extract_lunar_str(lunar) -> str | None:
    if lunar is None:
        return None
    try:
        month_cn = lunar.lunarMonthCn.replace("大", "").replace("小", "")
        return f"{lunar.lunarYearCn}【{lunar.chineseYearZodiac}】 {month_cn}{lunar.lunarDayCn}"
    except Exception:
        return None


def _extract_term_text(lunar) -> str | None:
    if lunar is None:
        return None
    term = getattr(lunar, "todaySolarTerms", "")
    if isinstance(term, list) and term:
        term = term[0]
    return term if term and term != "无" else None


def _extract_holidays(lunar, solar_date: date | None) -> tuple:
    if lunar is None:
        return (), ()
    try:
        legal_raw = [
            FESTIVAL_NAME_MAP.get(x, x)
            for x in _as_list(lunar.get_legalHolidays())
            if x and x != "无"
        ]

        if lunar_mod.is_new_year_eve(lunar, solar_date):
            legal_raw.append("除夕")

        ordinary_raw = [
            FESTIVAL_NAME_MAP.get(x, x)
            for x in _as_list(lunar.get_otherHolidays())
            if x and x != "无"
        ]

        lm = getattr(lunar, "lunarMonth", 0)
        ld = getattr(lunar, "lunarDay", 0)
        leap = bool(getattr(lunar, "isLunarLeapMonth", False))
        if not leap:
            name = LUNAR_FESTIVALS.get((lm, ld))
            if name:
                (legal_raw if name in RED_TEXT_SET else ordinary_raw).append(name)

        legal = tuple(dict.fromkeys(legal_raw))
        ordinary = tuple(dict.fromkeys(n for n in ordinary_raw if n not in legal))
        return legal, ordinary
    except Exception:
        return (), ()


def build_info_parts(
    lunar_obj,
    has_cnlunar: bool,
    solar_date: date | None = None,
) -> InfoParts:
    legal, ordinary = _extract_holidays(lunar_obj, solar_date)

    return InfoParts(
        lunar_str=_extract_lunar_str(lunar_obj),
        term_text=_extract_term_text(lunar_obj),
        has_lunar_data=lunar_obj is not None,
        lunar_lib_available=bool(has_cnlunar),
        legal_holiday_names=legal,
        ordinary_holiday_names=ordinary,
    )


def _span(color: str, label: str, value: str) -> str:
    body = f"{html.escape(label)}：{html.escape(value)}" if label else html.escape(value)
    return f"<span style='color:{color}'>{body}</span>"


def render_html(parts: InfoParts, resolver: ThemeResolver | None = None) -> str | None:
    if resolver is None:
        resolver = ThemeResolver(dict(DEFAULT_THEME))

    pieces = []
    if parts.lunar_str:
        pieces.append(_span(resolver.color("lunar_text_color"), "", parts.lunar_str))
    if parts.term_text:
        pieces.append(
            _span(resolver.color("solar_term_text_color"), tr("info.solar_term"), parts.term_text)
        )
    if parts.legal_holiday_names:
        pieces.append(
            _span(
                resolver.color("festival_red"),
                tr("info.festival"),
                "、".join(parts.legal_holiday_names),
            )
        )
    if parts.ordinary_holiday_names:
        pieces.append(
            _span(
                resolver.color("normal_num_color"),
                tr("info.festival"),
                "、".join(parts.ordinary_holiday_names),
            )
        )

    if not pieces:
        return None
    return "&nbsp;·&nbsp;".join(pieces)


def placeholder_key(parts: InfoParts) -> str:
    if not parts.lunar_lib_available:
        return "info.no_cnlunar"
    if not parts.has_lunar_data:
        return "info.lunar_unavailable"
    return "info.no_events"


def format_weather(city: str, temperature: float, description: str) -> str:
    """Render the concise weather status used alongside the info panel."""
    return f"{city} {temperature:.0f}℃ {description}"
