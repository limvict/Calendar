# coding: utf-8
"""状态展示：信息栏、日程标记、心情按钮与专注统计。"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from PyQt6.QtCore import Qt

from desktop_calendar.config.i18n import tr
from desktop_calendar.core import lunar as lunar_mod
from desktop_calendar.core.lunar import get_lunar_by_datetime
from desktop_calendar.ui import info_panel
from desktop_calendar.ui.dialogs import (
    MoodDialog,
)
from desktop_calendar.utils.logging_setup import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


class MainWindowStatusMixin:
    """状态展示：信息栏、日程标记、心情按钮与专注统计。"""

    def _refresh_schedule_markers(self, *_args) -> None:
        if not hasattr(self, "cal"):
            return
        if hasattr(self, "view_selector") and self.view_selector.currentData() == "year":
            year = self.cal.selectedDate().year()
            visible_start = date(year, 1, 1)
            visible_end = date(year, 12, 31)
        else:
            year, month = self.cal.yearShown(), self.cal.monthShown()
            first = date(year, month, 1)
            visible_start = first - timedelta(days=first.weekday())
            visible_end = visible_start + timedelta(days=41)
        try:
            markers = self._schedule_mgr.markers_between(visible_start, visible_end)
        except (OSError, ValueError, TypeError):
            logger.exception("读取日程标记失败")
            markers = {}
        self.cal.set_schedule_markers(markers)
        self._refresh_overview_views()

    def _refresh_overview_views(self) -> None:
        if hasattr(self, "week_view") and hasattr(self, "year_view"):
            self.week_view.refresh()
            self.year_view.refresh()

    def _refresh_schedule_ui(self) -> None:
        if not hasattr(self, "schedule_panel"):
            return
        self.schedule_panel.refresh(self.cal.selectedDate().toPyDate())
        self._refresh_schedule_markers()

    def _refresh_info_label(self, resolver=None):
        sel_date = self.cal.selectedDate()
        sel_py = date(sel_date.year(), sel_date.month(), sel_date.day())

        parts = info_panel.build_info_parts(
            lunar_obj=get_lunar_by_datetime((sel_date.year(), sel_date.month(), sel_date.day())),
            has_cnlunar=lunar_mod.HAS_CNLUNAR,
            solar_date=sel_py,
        )
        r = resolver if resolver is not None else self.theme_mgr.current.resolver
        html_text = info_panel.render_html(parts, resolver=r)
        if html_text is None:
            self.info_label.setTextFormat(Qt.TextFormat.PlainText)
            self.info_label.setText(tr(info_panel.placeholder_key(parts)))
            self.info_label.setToolTip("")
            return
        self.info_label.setTextFormat(Qt.TextFormat.RichText)
        self.info_label.setText(html_text)
        self.info_label.setToolTip(html_text)

    def on_calendar_select_changed(self):
        self._refresh_info_label()
        self._update_mood_button()
        self._refresh_overview_views()
        if hasattr(self, "schedule_panel"):
            self.schedule_panel.refresh(self.cal.selectedDate().toPyDate())

    # ---------- 考勤打卡 ----------

    def _open_mood_dialog(self) -> None:
        selected = self.cal.selectedDate().toPyDate()
        dialog = MoodDialog(self.mood_store, selected, self, bundle=self.theme_mgr.current)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()
            self._update_mood_button()

    def _update_mood_button(self) -> None:
        if not hasattr(self, "btn_mood"):
            return
        selected = self.cal.selectedDate().toPyDate()
        record = self.mood_store.get(selected)
        if not record:
            self.btn_mood.setText(tr("btn.mood"))
            self.btn_mood.setToolTip(tr("mood.prompt"))
            return
        label = tr(f"mood.option.{record['mood']}")
        self.btn_mood.setText(f"{tr('btn.mood')} {label.split(' ', 1)[0]}")
        self.btn_mood.setToolTip(
            f"{selected.isoformat()} · {label}"
            + (f"\n{record['note']}" if record.get("note") else "")
        )

    def _update_focus_label(self) -> None:
        if not hasattr(self, "focus_status_label"):
            return
        count = self.focus_log.today_count()
        minutes = self.focus_log.today_minutes()
        if count:
            duration = f"{minutes // 60}h{minutes % 60:02d}m"
            self.focus_status_label.setText(tr("focus.today_stats", n=count, hm=duration))
        else:
            self.focus_status_label.setText(tr("focus.empty"))
