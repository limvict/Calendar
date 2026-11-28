# coding: utf-8
"""新增 / 编辑单个重要日子的对话框。"""

from __future__ import annotations

import calendar

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_calendar.config.constants import REFERENCE_LEAP_YEAR
from desktop_calendar.config.i18n import tr
from desktop_calendar.config.manager import get_logger
from desktop_calendar.core.important_days import (
    REPEAT_MONTH,
    REPEAT_ONCE,
    REPEAT_WEEK,
    REPEAT_YEAR,
    normalize_important_day,
)
from desktop_calendar.ui.theme import ThemeBundle

from ..base import (
    make_button_box,
)
from ..messages import msg_warn

logger = get_logger()

# 卡片强调色候选：与侧栏自动配色同源，保证手选和自动看起来是一套
_COLOR_CHOICES = ("", "#D47026", "#C25B5B", "#C08A2E", "#7C6BB0", "#5C7FB8", "#5C9EAD")


# ===================== 新增/编辑弹窗 =====================
class AddImportantDayDialog(QDialog):
    def __init__(self, parent=None, bundle: ThemeBundle = None):
        super().__init__(parent)
        if bundle is None:
            raise ValueError("AddImportantDayDialog 需要 ThemeBundle")
        self._bundle = bundle
        self._saved_type_lunar = False
        self._saved_isleap = False
        self._last_repeat_type = None

        dlg = self._bundle.dialog
        self.setWindowTitle(tr("important_day.title_new"))
        self.resize(*dlg.new_size)
        self.setStyleSheet(dlg.qss_standard)
        scale = self._bundle.scale_factor

        layout = QVBoxLayout(self)
        # 表单行数多，边距与行距比通用对话框再紧一档，避免 500px 高的空窗
        margin = max(12, round(16 * scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(6, round(8 * scale)))

        group_main = QGroupBox(tr("important_day.details"), self)
        form_main = QFormLayout(group_main)
        form_main.setSpacing(max(4, round(6 * scale)))
        self.edit_name = QLineEdit(group_main)
        self.edit_name.setPlaceholderText(tr("important_day.name_placeholder"))
        form_main.addRow(tr("important_day.name"), self.edit_name)

        self.radio_solar = QRadioButton(tr("important_day.solar"))
        self.radio_lunar = QRadioButton(tr("important_day.lunar"))
        self.radio_solar.setChecked(True)
        self._type_group = QButtonGroup(self)
        self._type_group.addButton(self.radio_solar)
        self._type_group.addButton(self.radio_lunar)

        self.chk_leap = QCheckBox(tr("important_day.leap"), group_main)
        self.chk_leap.setToolTip(tr("important_day.leap_tip"))
        self.chk_leap.setEnabled(False)
        self.radio_solar.toggled.connect(self._on_type_changed)
        self.radio_lunar.toggled.connect(self._on_type_changed)

        self.combo_repeat = QComboBox(group_main)
        self.combo_repeat.addItem(tr("important_day.repeat_year"), REPEAT_YEAR)
        self.combo_repeat.addItem(tr("important_day.repeat_month"), REPEAT_MONTH)
        self.combo_repeat.addItem(tr("important_day.repeat_week"), REPEAT_WEEK)
        self.combo_repeat.addItem(tr("important_day.repeat_once"), REPEAT_ONCE)
        self.combo_repeat.currentIndexChanged.connect(self._update_day_range)

        self.spin_month = QSpinBox(group_main)
        self.spin_month.setRange(1, 12)
        self.spin_month.setValue(1)
        self.spin_month.setMaximumWidth(max(64, round(86 * scale)))

        self.spin_day = QSpinBox(group_main)
        self.spin_day.setRange(1, 31)
        self.spin_day.setValue(1)
        self.spin_day.setMaximumWidth(max(64, round(86 * scale)))

        self.spin_advance = QSpinBox(group_main)
        self.spin_advance.setRange(0, 30)
        self.spin_advance.setValue(3)
        self.spin_advance.setMaximumWidth(max(64, round(88 * scale)))

        self.chk_enabled = QCheckBox(tr("important_day.enabled"), self)
        self.chk_enabled.setChecked(True)

        self.lbl_repeat = QLabel(tr("important_day.repeat"), group_main)
        self.lbl_month = QLabel(tr("important_day.month"), group_main)
        self.lbl_day = QLabel(tr("important_day.day"), group_main)
        self.lbl_advance = QLabel(tr("important_day.advance"))

        self.spin_year = QSpinBox(group_main)
        self.spin_year.setRange(1900, 2100)
        self.spin_year.setValue(QDate.currentDate().year())
        self.spin_year.setMaximumWidth(max(76, round(112 * scale)))
        self.lbl_year = QLabel(tr("important_day.year"), group_main)

        type_row = QHBoxLayout()
        type_row.addWidget(self.radio_solar)
        type_row.addWidget(self.radio_lunar)
        type_row.addWidget(self.chk_leap)
        type_row.addStretch(1)
        type_widget = QWidget(group_main)
        type_widget.setLayout(type_row)
        form_main.addRow(tr("important_day.type"), type_widget)
        form_main.addRow(self.lbl_repeat, self.combo_repeat)

        self.date_row = QWidget(group_main)
        date_layout = QHBoxLayout(self.date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(max(4, round(6 * scale)))
        for label, control in (
            (self.lbl_year, self.spin_year),
            (self.lbl_month, self.spin_month),
            (self.lbl_day, self.spin_day),
        ):
            date_layout.addWidget(label)
            date_layout.addWidget(control)
        date_layout.addStretch(1)
        form_main.addRow(tr("important_day.date"), self.date_row)

        self.spin_since = QSpinBox(group_main)
        self.spin_since.setRange(0, 2100)
        self.spin_since.setSpecialValueText(tr("important_day.since_year_special"))
        self.spin_since.setToolTip(tr("important_day.since_year_tip"))
        self.spin_since.setMaximumWidth(max(72, round(120 * scale)))
        self.lbl_since = QLabel(tr("important_day.since_year"), group_main)
        form_main.addRow(self.lbl_since, self.spin_since)

        self._build_style_row(form_main, group_main)
        layout.addWidget(group_main)

        group_reminder = QGroupBox(tr("important_day.reminder_settings"), self)
        reminder_layout = QFormLayout(group_reminder)
        reminder_layout.setSpacing(max(4, round(6 * scale)))
        reminder_layout.addRow(self.lbl_advance, self.spin_advance)
        reminder_layout.addRow(self.chk_enabled)
        layout.addWidget(group_reminder)

        self._btn_box = make_button_box(self, on_accept=self._on_accept)
        layout.addWidget(self._btn_box)
        self._update_day_range()

    def _build_style_row(self, form: QFormLayout, parent: QWidget) -> None:
        """颜色色块 + 置顶开关：卡片强调色与排序偏好。"""
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        resolver = self._bundle.resolver
        text_color = resolver.color("date_text_color")
        border_color = resolver.color("border_color")
        check_border = resolver.color("today_bg")
        scale = self._bundle.scale_factor
        swatch = max(14, round(20 * scale))
        auto_width = max(30, round(42 * scale))
        font_px = max(8, round(10 * scale))

        self._color_buttons: dict[str, QToolButton] = {}
        self._color_group = QButtonGroup(self)
        self._color_group.setExclusive(True)
        for color in _COLOR_CHOICES:
            button = QToolButton(row)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if color:
                button.setFixedSize(swatch, swatch)
                button.setToolTip(color)
                # 颜色选择器本身就是在选颜色，内联样式只服务于这个控件
                button.setStyleSheet(
                    f"QToolButton {{background-color: {color};"
                    f" border: 1px solid rgba(0,0,0,60); border-radius: {swatch // 2}px;}}"
                    f"QToolButton:checked {{border: 2px solid {check_border};}}"
                )
            else:
                button.setText(tr("important_day.color_auto"))
                button.setFixedSize(auto_width, swatch)
                button.setToolTip(tr("important_day.color_tip"))
                button.setStyleSheet(
                    f"QToolButton {{background: transparent; color: {text_color};"
                    f" border: 1px dashed {border_color}; border-radius: {swatch // 2}px;"
                    f" font-size: {font_px}px;}}"
                    f"QToolButton:checked {{border: 2px solid {check_border};}}"
                )
            self._color_buttons[color] = button
            self._color_group.addButton(button)
            layout.addWidget(button)

        layout.addSpacing(4)
        self.chk_pinned = QCheckBox(tr("important_day.pinned"), row)
        self.chk_pinned.setToolTip(tr("important_day.pinned_tip"))
        layout.addWidget(self.chk_pinned)
        layout.addStretch(1)
        form.addRow(tr("important_day.style"), row)

    def _select_color(self, color: str) -> None:
        button = self._color_buttons.get(color) or self._color_buttons.get("")
        if button is not None:
            button.setChecked(True)

    def _selected_color(self) -> str:
        for color, button in self._color_buttons.items():
            if button.isChecked():
                return color
        return ""

    def _on_type_changed(self):
        is_solar = self.radio_solar.isChecked()
        self.chk_leap.setEnabled(not is_solar)
        self._update_day_range()

    def _update_day_range(self, _idx: int = None):
        repeat_type = self.combo_repeat.currentData()
        was_week = self._last_repeat_type == REPEAT_WEEK
        is_week = repeat_type == REPEAT_WEEK
        is_once = repeat_type == REPEAT_ONCE

        if is_week and not was_week:
            self._saved_type_lunar = self.radio_lunar.isChecked()
            self._saved_isleap = self.chk_leap.isChecked()

        if is_week:
            self.spin_day.setMinimum(1)
            self.spin_day.setMaximum(7)
            # 说明放到标签/提示里：原来挂在 QSpinBox 上的长后缀会把日期行撑宽
            self.lbl_day.setText(tr("important_day.day_week"))
            self.spin_day.setToolTip(tr("important_day.weekday_tip"))
            self.spin_month.setEnabled(False)
            self.spin_month.setVisible(False)
            self.lbl_month.setVisible(False)
            self.spin_year.setVisible(False)
            self.lbl_year.setVisible(False)
            self.spin_year.setSuffix("")
            self.spin_month.setSuffix("")
            self.spin_day.setSuffix("")

            self.radio_solar.blockSignals(True)
            self.radio_lunar.blockSignals(True)
            try:
                self.radio_solar.setChecked(True)
            finally:
                self.radio_solar.blockSignals(False)
                self.radio_lunar.blockSignals(False)
            self.radio_lunar.setEnabled(False)
            self.chk_leap.setEnabled(False)
            self.chk_leap.setChecked(False)
        else:
            self.spin_day.setMinimum(1)
            # lunar 上限 30、solar 上限 31；once 已强制 solar，不受影响。
            # 切到 lunar 时若当前值 > 30，Qt 会自动截断到 30。
            is_lunar = self.radio_lunar.isChecked()
            self.spin_day.setMaximum(30 if is_lunar else 31)
            self.lbl_day.setText(tr("important_day.day"))
            self.spin_day.setToolTip("")
            self.spin_month.setEnabled(repeat_type in (REPEAT_YEAR, REPEAT_ONCE))
            self.spin_year.setVisible(is_once)
            # once 模式把「年/月/日」收进输入框后缀，隐藏三个字段标签，
            # 否则三个标签 + 三个输入框在 420px 宽里放不下。
            self.lbl_year.setVisible(False)
            self.lbl_month.setVisible(not is_once)
            self.lbl_day.setVisible(not is_once)
            self.spin_month.setVisible(True)
            self.spin_year.setEnabled(is_once)
            self.spin_year.setSuffix(tr("important_day.unit_year") if is_once else "")
            self.spin_month.setSuffix(tr("important_day.unit_month") if is_once else "")
            self.spin_day.setSuffix(tr("important_day.unit_day") if is_once else "")
            self.radio_lunar.setEnabled(not is_once)

            if is_once:
                # once 强制公历；blockSignals 避免触发 _on_type_changed
                self.radio_solar.blockSignals(True)
                try:
                    self.radio_solar.setChecked(True)
                finally:
                    self.radio_solar.blockSignals(False)
                self.chk_leap.setEnabled(False)
                self.chk_leap.setChecked(False)
            else:
                if was_week and self._saved_type_lunar:
                    self.radio_lunar.blockSignals(True)
                    try:
                        self.radio_lunar.setChecked(True)
                    finally:
                        self.radio_lunar.blockSignals(False)
                if was_week and self.radio_lunar.isChecked() and self._saved_isleap:
                    self.chk_leap.setChecked(True)
                self.chk_leap.setEnabled(self.radio_lunar.isChecked())

        is_year = repeat_type == REPEAT_YEAR
        self.spin_since.setEnabled(is_year)
        if not is_year:
            self.spin_since.setValue(0)
        self._last_repeat_type = repeat_type

    def _on_accept(self):
        if not self.edit_name.text().strip():
            msg_warn(self, tr("msg.hint"), tr("msg.name_empty"))
            return

        repeat_type = self.combo_repeat.currentData()
        is_solar = self.radio_solar.isChecked()

        if repeat_type == REPEAT_ONCE:
            year, month, day = (
                self.spin_year.value(),
                self.spin_month.value(),
                self.spin_day.value(),
            )
            try:
                last_day = calendar.monthrange(year, month)[1]
            except Exception:
                last_day = 28
            if day > last_day:
                msg_warn(
                    self,
                    tr("msg.hint"),
                    tr("important_day.warn_once_date").format(
                        year=year, month=month, day=day, max_day=last_day
                    ),
                )
                return

        elif repeat_type == REPEAT_YEAR:
            month, day = self.spin_month.value(), self.spin_day.value()
            if is_solar:
                _, last_day = calendar.monthrange(REFERENCE_LEAP_YEAR, month)
                if day > last_day:
                    msg_warn(
                        self,
                        tr("msg.hint"),
                        tr("important_day.warn_solar_day").format(
                            month=month, day=day, max_day=last_day
                        ),
                    )
                    return
            else:
                if day > 30:
                    msg_warn(self, tr("msg.hint"), tr("important_day.warn_lunar_day_max"))
                    return
                if self.chk_leap.isChecked():
                    reply = QMessageBox.question(
                        self,
                        tr("msg.hint"),
                        tr("important_day.warn_leap_rare"),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return
        elif repeat_type == REPEAT_MONTH:
            day = self.spin_day.value()
            if is_solar:
                if day > 28:
                    reply = QMessageBox.question(
                        self,
                        tr("msg.hint"),
                        tr("important_day.warn_day_overflow").format(day=day),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return
            elif day > 30:
                msg_warn(self, tr("msg.hint"), tr("important_day.warn_lunar_day_max_short"))
                return
        self.accept()

    def load_data(self, data: dict):
        frozen = (self.radio_solar, self.radio_lunar, self.combo_repeat)
        for w in frozen:
            w.blockSignals(True)
        try:
            self.edit_name.setText(data.get("name", ""))
            typ = data.get("type", "solar")
            if typ == "solar":
                self.radio_solar.setChecked(True)
            else:
                self.radio_lunar.setChecked(True)
            self.chk_leap.setChecked(bool(data.get("isleap", False)) if typ == "lunar" else False)
            idx = self.combo_repeat.findData(data.get("repeat_type", REPEAT_YEAR))
            if idx >= 0:
                self.combo_repeat.setCurrentIndex(idx)
            self.spin_month.setValue(data.get("month", 1))
            self.spin_day.setValue(data.get("day", 1))
            self.spin_advance.setValue(data.get("advance_days", 0))
            self.chk_enabled.setChecked(data.get("enabled", True))
            self.chk_pinned.setChecked(bool(data.get("pinned", False)))
            self._select_color(str(data.get("color") or "").upper())
            try:
                since_val = int(data.get("since_year") or 0)
            except (TypeError, ValueError):
                since_val = 0
            self.spin_since.setValue(max(0, min(self.spin_since.maximum(), since_val)))
            try:
                year_val = int(data.get("year") or QDate.currentDate().year())
            except (TypeError, ValueError):
                year_val = QDate.currentDate().year()
            self.spin_year.setValue(year_val)
        finally:
            for w in frozen:
                w.blockSignals(False)
        self._last_repeat_type = None
        self._update_day_range()

    def get_data(self) -> dict:
        typ = "solar" if self.radio_solar.isChecked() else "lunar"
        repeat_type = self.combo_repeat.currentData()
        if repeat_type == REPEAT_WEEK:
            typ = "solar"
        raw = {
            "name": self.edit_name.text().strip(),
            "type": typ,
            "month": self.spin_month.value(),
            "day": self.spin_day.value(),
            "isleap": self.chk_leap.isChecked() if typ == "lunar" else False,
            "advance_days": self.spin_advance.value(),
            "enabled": self.chk_enabled.isChecked(),
            "repeat_type": repeat_type,
            "pinned": self.chk_pinned.isChecked(),
            "color": self._selected_color(),
            # 0 在 normalize 里等价于「不计算周年」
            "since_year": self.spin_since.value() if repeat_type == REPEAT_YEAR else 0,
        }
        if repeat_type == REPEAT_ONCE:
            raw["year"] = self.spin_year.value()
        return normalize_important_day(raw)
