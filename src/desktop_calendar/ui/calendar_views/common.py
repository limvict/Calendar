# coding: utf-8
"""周/年视图共用的常量、日期计算与绘制外壳。"""

from __future__ import annotations

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget

from desktop_calendar.config.i18n import tr
from desktop_calendar.ui.theme import ThemeBundle

_WEEKDAY_NAMES = tuple(tr(f"weekday.short.{day}") for day in range(1, 8))
_SCHEDULE_DEFAULT = "#4A90D9"


def week_start(value: QDate) -> QDate:
    return value.addDays(1 - value.dayOfWeek())


class CalendarViewBase(QWidget):
    """周/年视图共用的外壳：主题切换、壁纸、鼠标形态与字号换算。

    两个视图只在绘制与命中测试上不同，这里集中处理完全一致的部分，
    避免同一份 apply_theme / set_wallpaper / _font 各写一遍后逐渐走样。
    """

    #: 字号下限（pt）：周视图格子小，允许更小的字
    _FONT_MIN = 8.0

    def __init__(self, calendar, bundle: ThemeBundle, parent=None) -> None:
        super().__init__(parent)
        self._calendar = calendar
        self._bundle = bundle
        self._wallpaper = None
        self._wallpaper_overlay = 58
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def apply_theme(self, bundle: ThemeBundle) -> None:
        self._bundle = bundle
        self.update()

    def refresh(self) -> None:
        self.update()

    def set_wallpaper(self, pixmap, overlay_percent: int) -> None:
        self._wallpaper = pixmap
        self._wallpaper_overlay = overlay_percent
        self.update()

    def _font(self, size: int, *, bold: bool = False) -> QFont:
        font = QFont(self._bundle.fonts.global_)
        font.setPointSizeF(max(self._FONT_MIN, size * self._bundle.scale_factor))
        font.setBold(bold)
        return font
