# coding: utf-8
"""快捷侧栏 QSS：面板、标题、分区标题、状态卡与操作按钮。"""

from __future__ import annotations

from ..resolver import ThemeResolver
from .palette import _ensure_contrast, _get_safe_palette, _hover_accent


def sidebar_panel(r: ThemeResolver, *, rounded: bool = True) -> str:
    """右侧快捷侧边栏面板；收起时不需要圆角。"""
    radius = r.px("corner_radius") if rounded else "0px"
    return f"""
    #quick_sidebar {{
        background-color: {r.color("bg_main")};
        border-left: 1px solid {r.color("border_color")};
        border-top-right-radius: {radius};
        border-bottom-right-radius: {radius};
    }}
    """


def sidebar_close_button(r: ThemeResolver) -> str:
    return f"""
    QPushButton {{
        background: {r.color("input_bg")};
        color: {r.color("date_text_color")};
        border: 1px solid {r.color("border_color")};
        border-radius: 8px;
        font-size: 18px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {r.color("btn_hover")};
        border-color: {_hover_accent(r)};
    }}
    QPushButton:focus {{
        border-color: {_hover_accent(r)};
    }}
    """


def sidebar_action_button(r: ThemeResolver) -> str:
    """侧边栏「常用」网格里的功能按钮。"""
    return f"""
    QPushButton {{
        background-color: {r.color("btn_bg")};
        color: {_ensure_contrast(r.color("btn_bg"), r.color("btn_text"))};
        border: 1px solid transparent;
        border-radius: 9px;
        padding: 8px 11px;
        font-size: 12px;
        text-align: left;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {r.color("btn_hover")};
        border-color: {_hover_accent(r)};
    }}
    QPushButton:focus {{
        border-color: {_hover_accent(r)};
    }}
    QPushButton:pressed {{
        background-color: {r.color("btn_pressed")};
    }}
    """


def sidebar_section_title(r: ThemeResolver) -> str:
    """侧边栏区块标题（天气 / 今日状态 / 专注 / 常用）。"""
    return f"""
    QLabel {{
        color: {r.color("date_text_color")};
        font-size: {r.px("sidebar_section_font_size")};
        font-weight: 600;
        padding: 3px 2px;
        border-bottom: 1px solid {r.color("border_color")};
        background: transparent;
    }}
    """


def sidebar_status_card(r: ThemeResolver) -> str:
    """侧边栏里的状态卡片（考勤 / 专注）。"""
    return f"""
    QLabel {{
        background-color: {r.color("input_bg")};
        color: {r.color("date_text_color")};
        border: 1px solid {r.color("border_color")};
        border-radius: 10px;
        font-size: 12px;
        padding: 10px;
    }}
    """


def sidebar_title(r: ThemeResolver) -> str:
    return f"""
    QLabel {{
        font-size: 18px;
        font-weight: 700;
        color: {r.color("date_text_color")};
        padding: 0;
        background: transparent;
    }}
    """


def sidebar_subtitle(r: ThemeResolver) -> str:
    return f"""
    QLabel {{
        font-size: 11px;
        color: {r.color("date_text_color")};
        background: transparent;
    }}
    """


def important_days(r: ThemeResolver) -> str:
    """侧栏重要日子卡片：折叠标题 + 倒数卡片 + 空状态。"""
    p = _get_safe_palette(r)
    border = r.color("border_color")
    accent = _hover_accent(r)
    # 今日卡片用主题高亮色的低透明度铺底：直接写 today_bg 会盖住文字
    today = r.qcolor("today_bg")
    today_tint = f"rgba({today.red()}, {today.green()}, {today.blue()}, 0.12)"
    return f"""
    #important_days {{
        background: transparent;
    }}
    QWidget#important_days_header {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {border};
    }}
    QToolButton#important_days_toggle {{
        color: {p.text_main};
        background: transparent;
        border: none;
        padding: 3px 2px;
        font-size: {r.px("sidebar_section_font_size")};
        font-weight: 600;
        text-align: left;
    }}
    QToolButton#important_days_toggle:hover {{
        color: {accent};
    }}
    QLabel#important_days_count {{
        color: {r.color("normal_lunar_color")};
        font-size: {r.px("small_font_size")};
        background: transparent;
    }}
    QPushButton#important_days_manage {{
        color: {p.text_input};
        background: transparent;
        border: none;
        font-size: {r.px("small_font_size")};
        padding: 2px 4px;
    }}
    QPushButton#important_days_manage:hover {{
        color: {accent};
    }}
    QWidget#important_days_body {{
        background: transparent;
    }}
    QFrame#important_day_card {{
        background-color: {p.bg_input};
        border: 1px solid {border};
        border-radius: {r.px("btn_radius")};
    }}
    QFrame#important_day_card:hover {{
        background-color: {r.color("btn_hover")};
        border-color: {accent};
    }}
    QFrame#important_day_card[today="true"] {{
        background-color: {today_tint};
        border-color: {accent};
    }}
    QLabel#important_day_card_name {{
        color: {p.text_input};
        font-size: {r.px("font_size")};
        font-weight: 600;
        background: transparent;
    }}
    QLabel#important_day_card_meta {{
        color: {r.color("normal_lunar_color")};
        font-size: {r.px("small_font_size")};
        background: transparent;
    }}
    QLabel#important_day_card_pin {{
        color: {r.color("festival_red")};
        font-size: {r.px("small_font_size")};
        background: transparent;
    }}
    QLabel#important_days_empty {{
        color: {r.color("normal_lunar_color")};
        font-size: {r.px("small_font_size")};
        background: transparent;
        padding: 2px;
    }}
    QPushButton#important_days_more, QPushButton#important_days_empty_add {{
        color: {accent};
        background: transparent;
        border: none;
        font-size: {r.px("small_font_size")};
        padding: 2px;
        text-align: left;
    }}
    QPushButton#important_days_more:hover, QPushButton#important_days_empty_add:hover {{
        color: {r.color("today_bg")};
    }}
    """


def attendance_punch_button(r: ThemeResolver) -> str:
    """「今日状态」下方的上/下班双按钮：等宽、居中、带禁用态。"""
    return f"""
    QPushButton {{
        background-color: {r.color("btn_bg")};
        color: {_ensure_contrast(r.color("btn_bg"), r.color("btn_text"))};
        border: 1px solid transparent;
        border-radius: 9px;
        padding: 7px 6px;
        font-size: 12px;
        font-weight: 500;
        text-align: center;
    }}
    QPushButton:hover {{
        background-color: {r.color("btn_hover")};
        border-color: {_hover_accent(r)};
    }}
    QPushButton:pressed {{
        background-color: {r.color("btn_pressed")};
    }}
    QPushButton:focus {{
        border-color: {_hover_accent(r)};
    }}
    QPushButton:disabled {{
        background-color: {r.color("btn_disabled_bg")};
        color: {r.color("btn_disabled_text")};
        border-color: {r.color("btn_disabled_border")};
    }}
    """


def attendance_stats_link(r: ThemeResolver) -> str:
    """统计行右侧的「统计」文字入口：无边框，hover 用强调色。"""
    return f"""
    QPushButton {{
        background: transparent;
        border: none;
        color: {r.color("date_text_color")};
        font-size: 11px;
        padding: 2px 6px;
    }}
    QPushButton:hover {{
        color: {_hover_accent(r)};
    }}
    QPushButton:pressed {{
        color: {_hover_accent(r)};
    }}
    """
