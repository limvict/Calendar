"""番茄钟状态机：纯 QObject，界面无关。"""

from __future__ import annotations

import math
import time
from enum import StrEnum

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..config.constants import (
    POMODORO_LONG_BREAK_MINUTES_DEFAULT,
    POMODORO_ROUNDS_BEFORE_LONG_DEFAULT,
    POMODORO_SHORT_BREAK_MINUTES_DEFAULT,
    POMODORO_WORK_MINUTES_DEFAULT,
)

# Windows 上 time.monotonic() 精度约 15.6ms：暂停/刚启动时 deadline 与 now
# 可能取到同一个时钟值，浮点减法会残留 1e-12 级误差，直接 ceil 会多出 1 秒。
_CLOCK_EPSILON = 1e-6


def _ceil_seconds(seconds: float) -> int:
    """向上取整到秒，同时抹掉时钟精度带来的"差一丁点"误差。"""
    return max(0, math.ceil(seconds - _CLOCK_EPSILON))


class Phase(StrEnum):
    IDLE = "idle"
    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


class PomodoroTimer(QObject):
    """按「截止时刻」计时，而不是每秒减一。

    QTimer 在 Windows 上默认是粗粒度定时器，单次可能晚十几毫秒；如果每秒
    `-1`，25 分钟下来会慢几十秒。这里用 `time.monotonic()` 记截止时刻，
    每次 tick 只负责把剩余时间换算成秒数，误差不会累积。
    """

    tick = pyqtSignal(int, str)  # (剩余秒数, phase.value)
    phase_changed = pyqtSignal(str)  # 新阶段
    paused_changed = pyqtSignal(bool)
    round_finished = pyqtSignal(int)  # 完成的第 N 个番茄（只算自然完成）
    work_completed = pyqtSignal(int, int)  # 完成轮次与专注秒数
    phase_completed = pyqtSignal(str, bool)  # (结束的阶段, 是否自然结束)

    def __init__(
        self,
        work_min: int = POMODORO_WORK_MINUTES_DEFAULT,
        short_min: int = POMODORO_SHORT_BREAK_MINUTES_DEFAULT,
        long_min: int = POMODORO_LONG_BREAK_MINUTES_DEFAULT,
        rounds_before_long: int = POMODORO_ROUNDS_BEFORE_LONG_DEFAULT,
        parent=None,
    ):
        super().__init__(parent)
        values = (work_min, short_min, long_min, rounds_before_long)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values
        ):
            raise ValueError("番茄钟时长和长休息轮数必须为正整数")
        self._cfg = {
            "work": work_min * 60,
            "short": short_min * 60,
            "long": long_min * 60,
            "rounds": rounds_before_long,
        }
        self._phase = Phase.IDLE
        self._remaining = 0
        self._deadline = 0.0
        self._round = 0
        self._paused = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    # ---- 查询 ----
    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def remaining(self) -> int:
        return self._remaining

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def round_index(self) -> int:
        return self._round

    @property
    def rounds_before_long(self) -> int:
        return self._cfg["rounds"]

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def duration_seconds(self, phase: Phase | str) -> int:
        value = phase.value if isinstance(phase, Phase) else phase
        return {
            "work": self._cfg["work"],
            "short_break": self._cfg["short"],
            "long_break": self._cfg["long"],
        }.get(value, 0)

    def is_break(self, phase: Phase | str | None = None) -> bool:
        value = phase or self._phase
        value = value.value if isinstance(value, Phase) else value
        return value in ("short_break", "long_break")

    # ---- 控制 ----
    def start(self) -> None:
        if self._phase == Phase.IDLE:
            self._enter(Phase.WORK)
        else:
            self._deadline = time.monotonic() + self._remaining
        self._paused = False
        self.paused_changed.emit(False)
        self._timer.start()

    def pause(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._remaining = _ceil_seconds(self._deadline - time.monotonic())
            self._paused = True
            self.paused_changed.emit(True)

    def reset(self) -> None:
        self._timer.stop()
        self._phase = Phase.IDLE
        self._remaining = 0
        self._deadline = 0.0
        self._round = 0
        self._paused = False
        self.phase_changed.emit(self._phase.value)
        self.paused_changed.emit(False)
        self.tick.emit(0, self._phase.value)

    def skip(self) -> None:
        """跳过当前阶段。

        专注阶段跳过 = 放弃本轮：不计数、不记时长，直接回到待开始；
        休息阶段跳过 = 提前结束休息，进入下一轮专注（自动开始）。
        """
        if self._phase == Phase.IDLE:
            return
        if self._phase == Phase.WORK:
            self._timer.stop()
            finished = self._phase
            self._phase = Phase.IDLE
            self._remaining = 0
            self._deadline = 0.0
            self._paused = False
            self.phase_completed.emit(finished.value, False)
            self.phase_changed.emit(Phase.IDLE.value)
            self.paused_changed.emit(False)
            self.tick.emit(0, Phase.IDLE.value)
            return
        self._advance(natural=False)

    def stop(self) -> None:
        self._timer.stop()

    # ---- 内部 ----
    def _enter(self, phase: Phase) -> None:
        self._phase = phase
        self._remaining = self.duration_seconds(phase)
        self._deadline = time.monotonic() + self._remaining
        self.phase_changed.emit(phase.value)
        self.tick.emit(self._remaining, phase.value)

    def _on_tick(self) -> None:
        self._remaining = _ceil_seconds(self._deadline - time.monotonic())
        self.tick.emit(self._remaining, self._phase.value)
        if self._remaining <= 0:
            self._advance(natural=True)

    def _advance(self, *, natural: bool = True) -> None:
        self._timer.stop()
        finished = self._phase
        if finished == Phase.WORK:
            if natural:
                self._round += 1
                self.round_finished.emit(self._round)
                self.work_completed.emit(self._round, self._cfg["work"])
                long_due = self._round % self._cfg["rounds"] == 0
            else:
                # 跳过的专注不进长休息节奏
                long_due = False
            next_phase = Phase.LONG_BREAK if long_due else Phase.SHORT_BREAK
        else:
            next_phase = Phase.WORK
        self.phase_completed.emit(finished.value, natural)
        self._enter(next_phase)
        self._timer.start()  # 自动进入下一阶段
