# coding: utf-8
"""重要日子列表管理对话框。"""

from __future__ import annotations

import copy
import time
from datetime import date
from typing import Any

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from desktop_calendar.config.constants import REFERENCE_LEAP_YEAR
from desktop_calendar.config.i18n import tr
from desktop_calendar.config.manager import get_logger
from desktop_calendar.core.important_days import (
    REPEAT_MONTH,
    REPEAT_ONCE,
    REPEAT_WEEK,
    REPEAT_YEAR,
    get_next_important_day_date,
)
from desktop_calendar.ui.theme import ThemeBundle

from ..base import (
    fit_dialog_to_screen,
    make_button_box,
)
from ..messages import msg_info
from .add import AddImportantDayDialog

logger = get_logger()

# 没有下一次发生日期的重要日子排在列表末尾
_NO_NEXT_DATE_RANK = 10**6


_NO_NEXT_DATE_RANK = 10**6


# ===================== 管理弹窗 =====================
class ImportantDaysDialog(QDialog):
    def __init__(self, important_day_list, parent=None, bundle: ThemeBundle = None):
        super().__init__(parent)
        if bundle is None:
            raise ValueError("ImportantDaysDialog 需要 ThemeBundle")
        self._bundle = bundle
        self.important_day_list = copy.deepcopy(important_day_list)

        dlg = self._bundle.dialog
        self.setWindowTitle(tr("important_day.title_manage"))
        self.resize(*dlg.manage_size)
        self.setStyleSheet(dlg.qss_manage)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(dlg.margin, dlg.margin, dlg.margin, dlg.margin)
        layout.setSpacing(dlg.spacing)

        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)
        scale = self._bundle.scale_factor
        self.list_widget.setSpacing(max(2, round(4 * scale)))
        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("important_days_summary")
        self.summary_label.setStyleSheet(
            f"color: {self._bundle.resolver.color('normal_lunar_color')};"
        )
        self.refresh_list()
        layout.addWidget(self.summary_label)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton(tr("btn.add"))
        self.btn_edit = QPushButton(tr("btn.edit"))
        self.btn_del = QPushButton(tr("btn.delete"))
        self.btn_all_enable = QPushButton(tr("btn.all_enable"))
        self.btn_all_disable = QPushButton(tr("btn.all_disable"))
        for b in (self.btn_add, self.btn_edit, self.btn_del):
            btn_layout.addWidget(b)
        layout.addLayout(btn_layout)
        bulk_layout = QHBoxLayout()
        bulk_layout.addWidget(self.btn_all_enable)
        bulk_layout.addWidget(self.btn_all_disable)
        bulk_layout.addStretch(1)
        layout.addLayout(bulk_layout)

        self._btn_box = make_button_box(self)
        layout.addWidget(self._btn_box)

        self.btn_add.clicked.connect(self.add_item)
        self.btn_edit.clicked.connect(self.edit_item)
        self.btn_del.clicked.connect(self.del_item)
        self.btn_all_enable.clicked.connect(self.batch_enable_all)
        self.btn_all_disable.clicked.connect(self.batch_disable_all)
        fit_dialog_to_screen(self, dlg.manage_size, minimum_size=(480, 320))

    def _sort_by_date(self):
        """按"启用优先 + 下次发生日期最近优先"排序。

        每条重要日子调一次 get_next_important_day_date；农历重要日子会触发
        _build_lunar_index(ly)，首次打开对话框且 LRU 未预热时可能慢。
        耗时超 500ms 记 warning（根因在主窗口预热范围，本轮不改）；
        单条失败（数据损坏 / cnlunar 异常）排到末尾并记 warning，
        不让一条坏数据阻断整个管理对话框打开。

        normalized=False 是有意为之：本方法在 UI 边界，important_day_list
        可能被外部工具写入未归一化数据（缺 repeat_type 等字段）。
        normalize_important_day 开销微秒级，安全 > 微优化。
        """
        today = date.today()
        t0 = time.monotonic()
        failed_names = []

        def _sort_key(item: dict):
            disabled_rank = 0 if item.get("enabled", True) else 1
            try:
                target = get_next_important_day_date(
                    item, today, include_base=True, normalized=False
                )
            except Exception:
                failed_names.append(item.get("name") or "<unnamed>")
                logger.debug("重要日子排序时计算下次日期失败: %r", item, exc_info=True)
                target = None
            if target is None:
                return (disabled_rank, _NO_NEXT_DATE_RANK)
            return (disabled_rank, (target - today).days)

        self.important_day_list.sort(key=_sort_key)

        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms > 500:
            logger.warning(
                "重要日子排序耗时 %.1fms（%d 条），农历索引可能未预热",
                elapsed_ms,
                len(self.important_day_list),
            )
        if failed_names:
            logger.warning(
                "重要日子排序时 %d 条无法计算下次日期（已排到末尾）: %s",
                len(failed_names),
                ", ".join(failed_names[:5]),
            )

    @staticmethod
    def _clamp_weekday(day: Any) -> int:
        try:
            return max(1, min(7, int(day)))
        except (TypeError, ValueError):
            return 1

    def _format_item_text(self, item: dict, repeat_name_map: dict) -> str:
        tname = (
            tr("important_day.manage.type_solar")
            if item.get("type") == "solar"
            else tr("important_day.manage.type_lunar")
        )
        leap = tr("important_day.manage.leap_prefix") if item.get("isleap", False) else ""
        advance = item.get("advance_days", 0)
        status_text = (
            tr("important_day.manage.status_enabled")
            if item.get("enabled", True)
            else tr("important_day.manage.status_disabled")
        )
        repeat = repeat_name_map.get(
            item.get("repeat_type", REPEAT_YEAR), tr("important_day.manage.repeat_prefix_year")
        )

        if item.get("repeat_type") == REPEAT_WEEK:
            wd = self._clamp_weekday(item.get("day", 1))
            week_key = f"weekday.short.{wd}"
            week_text = tr(week_key)
            if week_text == week_key:
                week_text = str(wd)
            date_text = tr("important_day.manage.week_fmt").format(week=week_text)
        elif item.get("repeat_type") == REPEAT_ONCE:
            date_text = tr("important_day.manage.once_date_fmt").format(
                year=item.get("year", REFERENCE_LEAP_YEAR),
                month=item.get("month", 1),
                day=item.get("day", 1),
            )
        else:
            date_text = tr("important_day.manage.date_fmt").format(
                month=item.get("month", 1), day=item.get("day", 1)
            )

        # 类型 + 闰月前缀 + 日期由语言模板拼装：不同语言对空格 /
        # 分隔符的需求不同（中文零间距、英文需空格），硬拼会得到
        # "LunarLeap4/15" 这种粘连结果。
        type_date = tr("important_day.manage.type_date_fmt").format(
            type=tname, leap=leap, date=date_text
        )

        display_name = item.get("name") or tr("important_day.default_name")
        if item.get("pinned"):
            display_name = f"★ {display_name}"
        return (
            f"{status_text} · {display_name}\n"
            f"{repeat} · {type_date} · "
            f"{tr('important_day.manage.advance_fmt').format(advance=advance)}"
        )

    def _find_row_by_item(self, target: dict) -> int | None:
        for row, item in enumerate(self.important_day_list):
            if item == target:
                return row
        return None

    @staticmethod
    def _build_repeat_name_map() -> dict:
        return {
            REPEAT_YEAR: tr("important_day.manage.repeat_prefix_year"),
            REPEAT_MONTH: tr("important_day.manage.repeat_prefix_month"),
            REPEAT_WEEK: tr("important_day.manage.repeat_prefix_week"),
            REPEAT_ONCE: tr("important_day.manage.repeat_prefix_once"),
        }

    def refresh_list(self):
        self.list_widget.clear()
        self.important_day_list = [m for m in self.important_day_list if isinstance(m, dict)]
        self._sort_by_date()
        repeat_name_map = self._build_repeat_name_map()
        enabled_count = sum(bool(item.get("enabled", True)) for item in self.important_day_list)
        self.summary_label.setText(
            tr("important_day.manage.summary").format(
                total=len(self.important_day_list),
                enabled=enabled_count,
                disabled=len(self.important_day_list) - enabled_count,
            )
        )
        for item in self.important_day_list:
            text = self._format_item_text(item, repeat_name_map)
            list_item = QListWidgetItem(text, self.list_widget)
            list_item.setSizeHint(QSize(0, max(36, round(58 * self._bundle.scale_factor))))
            list_item.setToolTip(text.replace("\n", " · "))
            if not item.get("enabled", True):
                list_item.setForeground(self._bundle.resolver.qcolor("normal_lunar_color"))

    def add_item(self):
        dlg = AddImportantDayDialog(self, bundle=self._bundle)
        try:
            if not dlg.exec():
                return
            new_item = dlg.get_data()
        finally:
            dlg.deleteLater()
        self.important_day_list.append(new_item)
        self.refresh_list()
        row = self._find_row_by_item(new_item)
        if row is not None:
            self.list_widget.setCurrentRow(row)

    def edit_item(self):
        row = self.list_widget.currentRow()
        if row < 0:
            msg_info(self, tr("msg.hint"), tr("important_day.manage.select_first"))
            return
        dlg = AddImportantDayDialog(self, bundle=self._bundle)
        try:
            dlg.load_data(self.important_day_list[row])
            if not dlg.exec():
                return
            edited = dlg.get_data()
        finally:
            dlg.deleteLater()
        self.important_day_list[row] = edited
        self.refresh_list()
        new_row = self._find_row_by_item(edited)
        if new_row is not None:
            self.list_widget.setCurrentRow(new_row)

    def del_item(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        reply = QMessageBox.question(
            self,
            tr("important_day.manage.confirm_delete_title"),
            tr("important_day.confirm_delete"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del self.important_day_list[row]
        self.refresh_list()
        # refresh_list 会重排序，原 row 位置不一定还是同一条。这里选择
        # "选中原索引位置（或新的最后一条）"——与文件管理器等常见列表
        # 的删除行为一致：用户连按删除时焦点不会跳到列表顶部。
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(min(row, self.list_widget.count() - 1))

    def batch_enable_all(self):
        if not self.important_day_list:
            msg_info(self, tr("msg.hint"), tr("important_day.manage.empty"))
            return
        reply = QMessageBox.question(
            self,
            tr("msg.confirm"),
            tr("important_day.manage.confirm_enable_all"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for item in self.important_day_list:
                item["enabled"] = True
            self.refresh_list()

    def batch_disable_all(self):
        if not self.important_day_list:
            msg_info(self, tr("msg.hint"), tr("important_day.manage.empty"))
            return
        reply = QMessageBox.question(
            self,
            tr("msg.confirm"),
            tr("important_day.manage.confirm_disable_all"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for item in self.important_day_list:
                item["enabled"] = False
            self.refresh_list()

    def get_result(self):
        return self.important_day_list
