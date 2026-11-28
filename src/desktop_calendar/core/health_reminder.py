# coding: utf-8
"""久坐休息 / 喝水提醒：两个独立的单次定时器。

与番茄钟解耦：番茄钟管"专注-休息"节奏，这里管整天的健康提醒；两者可以
同时开，也可以在设置里单独关闭。
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..config.constants import (
    HEALTH_REST_INTERVAL_MAX,
    HEALTH_REST_INTERVAL_MIN,
    HEALTH_REST_INTERVAL_MINUTES_DEFAULT,
    HEALTH_WATER_INTERVAL_MAX,
    HEALTH_WATER_INTERVAL_MIN,
    HEALTH_WATER_INTERVAL_MINUTES_DEFAULT,
)
from ..config.manager import ConfigManager, get_logger, to_bool
from ..utils.coerce import to_int_clamped

logger = get_logger()


class HealthReminderManager(QObject):
    """按 ``health_cfg`` 调度休息 / 喝水提醒。

    每次触发后重新开始同一个定时器，不重置另一条提醒的倒计时。
    """

    rest_due = pyqtSignal()
    water_due = pyqtSignal()

    def __init__(self, parent, config: ConfigManager):
        super().__init__(parent)
        self._config = config
        self._shutting_down = False
        self._rest_timer = QTimer(self)
        self._rest_timer.setSingleShot(True)
        self._rest_timer.timeout.connect(self._on_rest_due)
        self._water_timer = QTimer(self)
        self._water_timer.setSingleShot(True)
        self._water_timer.timeout.connect(self._on_water_due)
        self.reschedule()

    def _read(self) -> tuple[bool, int, bool, int]:
        raw = self._config.get("health_cfg", {})
        cfg = raw if isinstance(raw, dict) else {}
        rest_enabled = to_bool(cfg.get("rest_enabled"), default=True)
        water_enabled = to_bool(cfg.get("water_enabled"), default=True)
        rest_min = to_int_clamped(
            cfg.get("rest_interval_min"),
            lo=HEALTH_REST_INTERVAL_MIN,
            hi=HEALTH_REST_INTERVAL_MAX,
            default=HEALTH_REST_INTERVAL_MINUTES_DEFAULT,
        )
        water_min = to_int_clamped(
            cfg.get("water_interval_min"),
            lo=HEALTH_WATER_INTERVAL_MIN,
            hi=HEALTH_WATER_INTERVAL_MAX,
            default=HEALTH_WATER_INTERVAL_MINUTES_DEFAULT,
        )
        return rest_enabled, rest_min, water_enabled, water_min

    def reschedule(self) -> None:
        if self._shutting_down:
            return
        rest_enabled, rest_min, water_enabled, water_min = self._read()
        self._rest_timer.stop()
        self._water_timer.stop()
        if rest_enabled:
            self._rest_timer.start(rest_min * 60_000)
        if water_enabled:
            self._water_timer.start(water_min * 60_000)

    def _on_rest_due(self) -> None:
        if self._shutting_down:
            return
        self.rest_due.emit()
        _, rest_min, _, _ = self._read()
        self._rest_timer.start(rest_min * 60_000)

    def _on_water_due(self) -> None:
        if self._shutting_down:
            return
        self.water_due.emit()
        _, _, _, water_min = self._read()
        self._water_timer.start(water_min * 60_000)

    def stop(self) -> None:
        self._shutting_down = True
        self._rest_timer.stop()
        self._water_timer.stop()
