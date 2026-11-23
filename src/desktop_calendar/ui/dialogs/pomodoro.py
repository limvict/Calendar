# coding: utf-8
"""专注计时对话框：环形进度 + 轮次 + 今日统计，跟随主题配色。"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...config.i18n import tr
from ...core.pomodoro import Phase, PomodoroTimer
from ..theme import ThemeBundle
from .base import fit_dialog_to_screen

__all__ = ["PomodoroDialog"]

_PHASE_KEYS = {
    Phase.IDLE.value: "pomodoro.phase_idle",
    Phase.WORK.value: "pomodoro.phase_work",
    Phase.SHORT_BREAK.value: "pomodoro.phase_short",
    Phase.LONG_BREAK.value: "pomodoro.phase_long",
}


class _Ring(QWidget):
    """环形进度：轨道 + 强调色进度弧，颜色由主题提供。"""

    def __init__(self, scale: float = 1.0, parent=None) -> None:
        super().__init__(parent)
        self.progress = 0.0
        self.track_color = QColor("#E0E0E0")
        self.accent_color = QColor("#E8564B")
        self.thickness = max(6, round(10 * scale))
        self._size = max(150, round(190 * scale))
        self.setMinimumSize(self._size, self._size)

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = self.thickness // 2 + 2
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.setPen(QPen(self.track_color, self.thickness))
        painter.drawArc(rect, 0, 360 * 16)
        if self.progress <= 0:
            return
        painter.setPen(QPen(self.accent_color, self.thickness))
        painter.drawArc(rect, 90 * 16, int(-360 * 16 * self.progress))


class PomodoroDialog(QDialog):
    def __init__(
        self,
        timer: PomodoroTimer,
        parent=None,
        focus_log=None,
        bundle: ThemeBundle | None = None,
    ):
        super().__init__(parent)
        self._t = timer
        self._focus_log = focus_log
        self._scale = getattr(bundle, "scale_factor", 1.0) if bundle is not None else 1.0
        self._resolver = bundle.resolver if bundle is not None else None

        self.setWindowTitle(tr("pomodoro.title"))
        self.resize(round(320 * self._scale), round(440 * self._scale))
        if bundle is not None:
            muted = bundle.resolver.color("normal_lunar_color")
            self.setStyleSheet(
                bundle.dialog.qss_standard
                + f"""
                QPushButton:disabled {{ color: {muted}; }}
                """
            )

        self._lbl_round = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._lbl_round.setObjectName("pomodoro_round")
        self._ring = _Ring(self._scale)
        self._lbl_time = QLabel("25:00", alignment=Qt.AlignmentFlag.AlignCenter)
        self._lbl_time.setObjectName("pomodoro_time")
        self._lbl_phase = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._lbl_phase.setObjectName("pomodoro_phase")
        self._lbl_stats = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._lbl_stats.setObjectName("pomodoro_stats")

        self._btn_start = QPushButton(tr("pomodoro.start"))
        self._btn_start.setObjectName("pomodoro_primary")
        self._btn_start.setDefault(True)
        self._btn_skip = QPushButton(tr("pomodoro.skip"))
        self._btn_reset = QPushButton(tr("pomodoro.reset"))

        layout = QVBoxLayout(self)
        layout.setSpacing(round(10 * self._scale))
        layout.addWidget(self._lbl_round)
        layout.addWidget(self._ring, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._lbl_time)
        layout.addWidget(self._lbl_phase)
        layout.addWidget(self._lbl_stats)
        row = QHBoxLayout()
        for button in (self._btn_start, self._btn_skip, self._btn_reset):
            row.addWidget(button)
        layout.addLayout(row)

        self._apply_theme_fonts()
        self._btn_start.clicked.connect(self._toggle)
        self._btn_reset.clicked.connect(self._reset)
        self._btn_skip.clicked.connect(timer.skip)
        timer.tick.connect(self._on_tick)
        timer.phase_changed.connect(self._on_phase)
        timer.paused_changed.connect(self._on_paused)
        timer.work_completed.connect(lambda *_args: self._refresh_stats())

        self._shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._shortcut.activated.connect(self._toggle)

        self._sync()
        self._refresh_stats()

    # ---- 主题 ----
    def _apply_theme_fonts(self) -> None:
        time_size = round(42 * self._scale)
        self._lbl_time.setStyleSheet(f"font-size:{time_size}px;font-weight:600;")
        self._lbl_round.setStyleSheet(f"font-size:{round(12 * self._scale)}px;")
        self._lbl_phase.setStyleSheet(f"font-size:{round(14 * self._scale)}px;font-weight:500;")
        self._lbl_stats.setStyleSheet(f"font-size:{round(12 * self._scale)}px;")
        if self._resolver is not None:
            muted = self._resolver.color("normal_lunar_color")
            self._lbl_round.setStyleSheet(self._lbl_round.styleSheet() + f"color:{muted};")
            self._lbl_stats.setStyleSheet(self._lbl_stats.styleSheet() + f"color:{muted};")
            self._lbl_time.setStyleSheet(
                self._lbl_time.styleSheet() + f"color:{self._resolver.color('dialog_text')};"
            )
            self._lbl_phase.setStyleSheet(
                self._lbl_phase.styleSheet() + f"color:{self._resolver.color('dialog_text')};"
            )
            accent = self._resolver.color("today_bg")
            accent_text = self._resolver.color("today_text_color")
            self._btn_start.setStyleSheet(
                f"QPushButton{{background:{accent};color:{accent_text};border:none;"
                f"border-radius:8px;padding:8px 14px;font-weight:600;}}"
                f"QPushButton:hover{{background:{self._resolver.color('btn_hover')};}}"
                f"QPushButton:disabled{{background:{self._resolver.color('btn_disabled_bg')};"
                f"color:{self._resolver.color('btn_disabled_text')};}}"
            )
            self._ring.track_color = QColor(self._resolver.color("border_color"))
            self._ring.accent_color = QColor(
                self._resolver.color("today_bg")
                if self._t.phase == Phase.WORK
                else self._resolver.color("solar_term_text_color")
            )

    # ---- 状态同步 ----
    def _sync(self) -> None:
        self._on_phase(self._t.phase.value)
        self._on_paused(self._t.paused)
        self._on_tick(self._t.remaining, self._t.phase.value)

    def _on_phase(self, phase: str) -> None:
        self._lbl_phase.setText(tr(_PHASE_KEYS.get(phase, "pomodoro.phase_idle")))
        self._lbl_round.setText(
            tr("pomodoro.round").format(
                current=min(self._t.round_index + 1, self._t.rounds_before_long),
                total=self._t.rounds_before_long,
            )
        )
        self._btn_skip.setEnabled(phase != Phase.IDLE.value)
        self._btn_reset.setEnabled(phase != Phase.IDLE.value)
        if self._resolver is not None:
            # 专注用主题强调色，休息换一个柔和色，进度弧一眼能区分阶段
            self._ring.accent_color = QColor(
                self._resolver.color("today_bg")
                if phase == Phase.WORK.value
                else self._resolver.color("solar_term_text_color")
            )
        self._on_paused(self._t.paused)

    def _on_paused(self, paused: bool) -> None:
        if paused:
            self._btn_start.setText(tr("pomodoro.resume"))
            self._lbl_phase.setText(tr("pomodoro.paused"))
        else:
            self._btn_start.setText(
                tr("pomodoro.start") if self._t.phase == Phase.IDLE else tr("pomodoro.pause")
            )
            self._lbl_phase.setText(tr(_PHASE_KEYS.get(self._t.phase.value, "pomodoro.phase_idle")))
        self._btn_reset.setEnabled(self._t.phase != Phase.IDLE)

    def _on_tick(self, seconds: int, phase: str) -> None:
        total = self._t.duration_seconds(phase)
        if phase == Phase.IDLE.value:
            # 待开始时展示下一轮专注的时长，避免出现 00:00
            seconds = self._t.duration_seconds(Phase.WORK)
            total = seconds
        self._lbl_time.setText(f"{seconds // 60:02d}:{seconds % 60:02d}")
        self._ring.progress = 1 - seconds / total if total else 0.0
        self._ring.update()

    def _refresh_stats(self) -> None:
        if self._focus_log is None:
            self._lbl_stats.hide()
            return
        self._lbl_stats.show()
        count = self._focus_log.today_count()
        minutes = self._focus_log.today_minutes()
        if count:
            self._lbl_stats.setText(
                tr("focus.today_stats", n=count, hm=f"{minutes // 60}h{minutes % 60:02d}m")
            )
        else:
            self._lbl_stats.setText(tr("focus.empty"))

    # ---- 交互 ----
    def _toggle(self) -> None:
        if self._t.paused or self._t.phase == Phase.IDLE:
            self._t.start()
        else:
            self._t.pause()

    def _reset(self) -> None:
        self._t.reset()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        fit_dialog_to_screen(
            self,
            (round(320 * self._scale), round(440 * self._scale)),
            minimum_size=(round(280 * self._scale), round(380 * self._scale)),
        )
