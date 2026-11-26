# coding: utf-8
"""侧栏「重要日子」卡片区：倒数环、置顶、今日高亮与周年标签。

数据由 `core.important_days.cards` 组装（纯逻辑），这里只负责排版与文案。
卡片点击后跳到下一次发生日期；「管理」打开重要日子管理对话框。
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QDate, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...config.i18n import tr
from ...core.important_days import (
    REPEAT_MONTH,
    REPEAT_ONCE,
    REPEAT_WEEK,
    REPEAT_YEAR,
    ImportantDayCardData,
    build_important_day_cards,
)
from ..theme import ThemeBundle
from .elided_label import ElidedLabel

# 侧栏最多同时显示几张卡片，其余折叠到「查看全部」
_MAX_VISIBLE_CARDS = 4
# 跨天检查：卡片上的倒数要跟着日期变，侧栏长期开着也不能停在昨天
_DAY_CHECK_INTERVAL_MS = 30 * 60 * 1000

# 自动配色：公历偏暖、农历偏冷，同一类型里也按名称散开，避免一片同色
_SOLAR_ACCENTS = ("#D47026", "#C25B5B", "#C08A2E", "#A9744F", "#B3567A")
_LUNAR_ACCENTS = ("#7C6BB0", "#5C7FB8", "#5C9EAD", "#8A6F9E", "#4C8C7A")
_COLOR_FALLBACK = "#D47026"


def _auto_accent(name: str, mem_type: str) -> str:
    """按名称稳定散列到一组强调色：同一条重要日子每次打开颜色一致。"""
    palette = _LUNAR_ACCENTS if mem_type == "lunar" else _SOLAR_ACCENTS
    seed = 0
    for ch in name:
        seed = (seed * 131 + ord(ch)) & 0xFFFFFFFF
    return palette[seed % len(palette)]


def _repeat_text(card: ImportantDayCardData) -> str:
    key = {
        REPEAT_YEAR: "important_day.repeat_year_short",
        REPEAT_MONTH: "important_day.repeat_month_short",
        REPEAT_WEEK: "important_day.repeat_week_short",
        REPEAT_ONCE: "important_day.repeat_once_short",
    }.get(card.repeat_type, "important_day.repeat_year_short")
    return tr(key)


def _date_text(card: ImportantDayCardData) -> str:
    mem = card.important_day
    if card.repeat_type == REPEAT_WEEK:
        weekday = max(1, min(7, int(mem.get("day", 1) or 1)))
        return tr("important_day.cards.week_fmt").format(week=tr(f"weekday.short.{weekday}"))
    if card.repeat_type == REPEAT_ONCE:
        try:
            target = date(
                int(mem.get("year") or 1970), int(mem.get("month") or 1), int(mem.get("day") or 1)
            )
        except (TypeError, ValueError):
            return ""
        return tr("important_day.cards.date_once").format(
            year=target.year, month=target.month, day=target.day
        )
    if card.repeat_type == REPEAT_MONTH:
        key = (
            "important_day.cards.date_monthly_lunar"
            if card.type == "lunar"
            else "important_day.cards.date_monthly_solar"
        )
        return tr(key).format(day=mem.get("day", 1))
    if card.type == "lunar":
        leap = tr("important_day.manage.leap_prefix") if mem.get("isleap") else ""
        return tr("important_day.cards.date_lunar").format(
            leap=leap, month=mem.get("month", 1), day=mem.get("day", 1)
        )
    return tr("important_day.cards.date_solar").format(
        month=mem.get("month", 1), day=mem.get("day", 1)
    )


def _meta_text(card: ImportantDayCardData) -> str:
    parts = [_date_text(card)]
    # 每周 / 每月 的周期已经写在日期里，再拼「每周」「每月」会读成
    # 「每周三 · 每周」；只有每年 / 仅一次需要补周期说明。
    if card.repeat_type not in (REPEAT_WEEK, REPEAT_MONTH):
        parts.append(_repeat_text(card))
    if card.ordinal_years is not None and card.ordinal_years >= 1:
        parts.append(tr("important_day.cards.ordinal").format(years=card.ordinal_years))
    return " · ".join(part for part in parts if part)


def _when_text(card: ImportantDayCardData) -> str:
    if card.days is None:
        return tr("important_day.cards.when_none")
    if card.past:
        return tr("important_day.cards.when_past").format(days=abs(card.days))
    if card.days == 0:
        return tr("important_day.cards.when_today")
    return tr("important_day.cards.when_future").format(days=card.days)


def _tooltip_text(card: ImportantDayCardData) -> str:
    name = card.name or tr("important_day.default_name")
    lines = [name]
    if card.next_date is not None:
        lines.append(
            tr("important_day.cards.tip_date").format(
                date=card.next_date.strftime("%Y-%m-%d"), when=_when_text(card)
            )
        )
    type_text = (
        tr("important_day.manage.type_lunar")
        if card.type == "lunar"
        else tr("important_day.manage.type_solar")
    )
    lines.append(f"{_repeat_text(card)} · {type_text}")
    if card.ordinal_years is not None:
        lines.append(tr("important_day.cards.ordinal").format(years=card.ordinal_years))
    advance = int(card.important_day.get("advance_days", 0) or 0)
    if advance:
        lines.append(tr("important_day.cards.tip_advance").format(days=advance))
    else:
        lines.append(tr("important_day.cards.tip_advance_zero"))
    return "\n".join(lines)


class _CountdownRing(QWidget):
    """倒数环：外圈表示本轮周期进度，中间是剩余天数。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 纯装饰：鼠标事件交给卡片，否则点圆环不跳转
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._days: int | None = None
        self._past = False
        self._today = False
        self._progress: float | None = None
        self._accent = QColor(_COLOR_FALLBACK)
        self._track = QColor("#D8D2C5")
        self._muted = QColor("#808080")
        self._size = 46
        self.setFixedSize(self._size, self._size)

    def configure(
        self,
        card: ImportantDayCardData,
        *,
        accent: QColor,
        track: QColor,
        muted: QColor,
        size: int,
    ) -> None:
        self._days = card.days
        self._past = card.past
        self._today = card.days == 0 and not card.past
        self._progress = card.progress
        self._accent = accent
        self._track = track
        self._muted = muted
        self._size = max(28, int(size))
        self.setFixedSize(self._size, self._size)
        self.update()

    def paintEvent(self, event):  # noqa: N802 (Qt 接口)
        side = min(self.width(), self.height())
        if side <= 0:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen_width = max(3.0, side * 0.085)
            pad = pen_width / 2 + 1
            rect = QRectF(pad, pad, side - 2 * pad, side - 2 * pad)

            track_pen = QPen(self._track, pen_width)
            track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(track_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

            if self._progress is not None and self._progress > 0:
                arc_pen = QPen(self._accent, pen_width)
                arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(arc_pen)
                # 从 12 点方向顺时针填充
                painter.drawArc(rect, 90 * 16, -int(self._progress * 360 * 16))

            self._draw_text(painter, side)
        finally:
            painter.end()

    def _draw_text(self, painter: QPainter, side: int) -> None:
        if self._today:
            text, pt, unit = tr("important_day.cards.when_today"), 10.5, ""
        elif self._past:
            text, pt, unit = tr("important_day.cards.past_short"), 10.5, ""
        elif self._days is None:
            text, pt, unit = "—", 12.0, ""
        else:
            digits = str(self._days)
            text, unit = digits, tr("important_day.cards.unit_day")
            pt = 15.0 if len(digits) <= 2 else 11.5

        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(pt)
        painter.setFont(font)
        painter.setPen(self._muted if (self._past or self._days is None) else self._accent)
        if unit:
            painter.drawText(
                QRectF(0, -side * 0.06, side, side), Qt.AlignmentFlag.AlignCenter, text
            )
            unit_font = QFont(font)
            unit_font.setBold(False)
            unit_font.setPointSizeF(max(6.0, pt * 0.48))
            painter.setFont(unit_font)
            painter.setPen(self._muted)
            painter.drawText(
                QRectF(0, side * 0.56, side, side * 0.36),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                unit,
            )
        else:
            painter.drawText(QRectF(0, 0, side, side), Qt.AlignmentFlag.AlignCenter, text)


class ImportantDayCard(QFrame):
    """单张重要日子卡片。点击跳转到下一次发生日期。"""

    clicked = pyqtSignal(QDate)

    def __init__(self, card: ImportantDayCardData, bundle: ThemeBundle | None, parent=None):
        super().__init__(parent)
        self.setObjectName("important_day_card")
        self.setProperty("today", "true" if (card.days == 0 and not card.past) else "false")
        self._card = card
        self._target = card.next_date
        self._bundle = bundle
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._target is not None
            else Qt.CursorShape.ArrowCursor
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(_tooltip_text(card))

        scale = bundle.scale_factor if bundle is not None else 1.0
        metrics = bundle.layout if bundle is not None else None
        min_height = metrics.important_day_card_min_height if metrics is not None else 58
        margin_h = max(8, round(9 * scale))
        margin_v = max(6, round(7 * scale))
        self.setMinimumHeight(max(48, min_height))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin_h, margin_v, margin_h, margin_v)
        layout.setSpacing(max(8, round(9 * scale)))

        self._ring = _CountdownRing(self)
        layout.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(1)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(4)
        self._name_label = ElidedLabel(card.name or tr("important_day.default_name"), self)
        self._name_label.setObjectName("important_day_card_name")
        name_row.addWidget(self._name_label, 1)
        self._pin_label = QLabel("★", self)
        self._pin_label.setObjectName("important_day_card_pin")
        self._pin_label.setToolTip(tr("important_day.cards.pinned_tip"))
        self._pin_label.setVisible(card.pinned)
        name_row.addWidget(self._pin_label, 0, Qt.AlignmentFlag.AlignVCenter)
        text_box.addLayout(name_row)

        self._meta_label = ElidedLabel(_meta_text(card), self)
        self._meta_label.setObjectName("important_day_card_meta")
        text_box.addWidget(self._meta_label)

        layout.addLayout(text_box, 1)
        self._apply_ring_colors()

    def _apply_ring_colors(self) -> None:
        card = self._card
        bundle = self._bundle
        if bundle is not None:
            resolver = bundle.resolver
            track = resolver.qcolor("border_color")
            muted = resolver.qcolor("normal_lunar_color")
            accent = QColor(card.color) if card.color else QColor()
            if not accent.isValid():
                accent = QColor(_auto_accent(card.name, card.type))
            size = bundle.layout.important_day_ring_size
        else:
            track, muted = QColor("#D8D2C5"), QColor("#808080")
            accent = QColor(card.color) if card.color else QColor(_COLOR_FALLBACK)
            size = 46
        self._ring.configure(card, accent=accent, track=track, muted=muted, size=size)

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt 接口)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._target is not None
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit(QDate(self._target.year, self._target.month, self._target.day))
        super().mouseReleaseEvent(event)


class ImportantDaysWidget(QWidget):
    """侧栏重要日子卡片区：折叠标题、卡片列表、空状态与「查看全部」。"""

    activated = pyqtSignal(QDate)
    manage_requested = pyqtSignal()
    add_requested = pyqtSignal()

    def __init__(self, important_days=None, parent=None):
        super().__init__(parent)
        self.setObjectName("important_days")
        self._important_days = (
            list(important_days) if isinstance(important_days, (list, tuple)) else []
        )
        self._bundle: ThemeBundle | None = None
        self._today = date.today()
        self._build_ui()
        self._rebuild()

        self._day_timer = QTimer(self)
        self._day_timer.setInterval(_DAY_CHECK_INTERVAL_MS)
        self._day_timer.timeout.connect(self.refresh_if_new_day)
        self._day_timer.start()

    # ---------- 搭建 ----------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(4, 6))
        self._layout = layout

        header = QWidget(self)
        header.setObjectName("important_days_header")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        self._header_layout = header_layout
        header_layout.setContentsMargins(2, 0, 0, 4)
        header_layout.setSpacing(6)

        self._toggle = QToolButton(header)
        self._toggle.setObjectName("important_days_toggle")
        self._toggle.setText(tr("important_day.cards.title"))
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.toggled.connect(self._set_expanded)
        header_layout.addWidget(self._toggle)

        self._count_label = QLabel(self)
        self._count_label.setObjectName("important_days_count")
        header_layout.addWidget(self._count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_layout.addStretch(1)

        self._manage_button = QPushButton(tr("important_day.cards.manage"), header)
        self._manage_button.setObjectName("important_days_manage")
        self._manage_button.setFlat(True)
        self._manage_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manage_button.setToolTip(tr("important_day.cards.manage_tip"))
        self._manage_button.clicked.connect(self.manage_requested)
        header_layout.addWidget(self._manage_button)

        layout.addWidget(header)

        self._body = QWidget(self)
        self._body.setObjectName("important_days_body")
        self._body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body_layout = QVBoxLayout(self._body)
        self._body_layout = body_layout
        self._cards_layout = body_layout
        body_layout.setContentsMargins(0, 2, 0, 2)
        body_layout.setSpacing(6)
        layout.addWidget(self._body)

    def _set_expanded(self, checked: bool) -> None:
        self._body.setVisible(checked)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    # ---------- 数据 ----------
    def set_important_days(self, important_days) -> None:
        self._important_days = (
            list(important_days) if isinstance(important_days, (list, tuple)) else []
        )
        self._today = date.today()
        self._rebuild()

    def refresh_if_new_day(self) -> None:
        today = date.today()
        if today != self._today:
            self._today = today
            self._rebuild()

    def showEvent(self, event):  # noqa: N802 (Qt 接口)
        super().showEvent(event)
        self.refresh_if_new_day()

    # ---------- 主题 ----------
    def apply_theme(self, bundle: ThemeBundle) -> None:
        self._bundle = bundle
        self.setStyleSheet(bundle.qss.important_days)
        layout = bundle.layout
        self._layout.setSpacing(max(2, layout.important_day_body_spacing))
        self._header_layout.setSpacing(max(2, layout.saying_header_spacing))
        self._body_layout.setContentsMargins(*layout.important_day_body_margins)
        self._body_layout.setSpacing(layout.important_day_card_spacing)
        self._rebuild()

    # ---------- 列表 ----------
    def _clear_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._clear_cards()
        all_cards = build_important_day_cards(self._important_days, self._today)
        self._count_label.setText(
            tr("important_day.cards.count", n=len(all_cards)) if all_cards else ""
        )
        self._count_label.setVisible(bool(all_cards))

        if not all_cards:
            total = len([m for m in self._important_days if isinstance(m, dict)])
            text = (
                tr("important_day.cards.empty")
                if total == 0
                else tr("important_day.cards.all_disabled")
            )
            empty = QLabel(text, self._body)
            empty.setObjectName("important_days_empty")
            empty.setWordWrap(True)
            self._cards_layout.addWidget(empty)
            if total == 0:
                hint = QLabel(tr("important_day.cards.empty_hint"), self._body)
                hint.setObjectName("important_days_empty")
                hint.setWordWrap(True)
                self._cards_layout.addWidget(hint)
            add_button = QPushButton(tr("important_day.cards.add"), self._body)
            add_button.setObjectName("important_days_empty_add")
            add_button.setFlat(True)
            add_button.setCursor(Qt.CursorShape.PointingHandCursor)
            add_button.clicked.connect(self.add_requested)
            self._cards_layout.addWidget(add_button)
            return

        for card in all_cards[:_MAX_VISIBLE_CARDS]:
            widget = ImportantDayCard(card, self._bundle, self._body)
            widget.clicked.connect(self.activated)
            self._cards_layout.addWidget(widget)

        rest = len(all_cards) - _MAX_VISIBLE_CARDS
        if rest > 0:
            more = QPushButton(tr("important_day.cards.more", n=rest), self._body)
            more.setObjectName("important_days_more")
            more.setFlat(True)
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.clicked.connect(self.manage_requested)
            self._cards_layout.addWidget(more)
