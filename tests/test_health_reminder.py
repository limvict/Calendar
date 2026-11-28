# coding: utf-8
"""健康提醒：配置归一化 + 独立定时器。"""

from desktop_calendar.config.manager import normalize_config
from desktop_calendar.core.health_reminder import HealthReminderManager


class _Config:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}

    def get(self, key, default=None):
        return self.cfg.get(key, default)


def test_health_cfg_is_normalized_with_defaults_and_bounds():
    cfg = normalize_config({"health_cfg": {"rest_interval_min": 5, "water_enabled": "false"}})
    health = cfg["health_cfg"]
    assert health["rest_enabled"] is True
    assert health["water_enabled"] is False
    assert health["rest_interval_min"] == 20
    assert health["water_interval_min"] == 60


def test_health_reminder_starts_independent_timers(qapp):
    cfg = _Config(
        {
            "health_cfg": {
                "rest_enabled": True,
                "rest_interval_min": 30,
                "water_enabled": True,
                "water_interval_min": 60,
            }
        }
    )
    mgr = HealthReminderManager(None, cfg)
    try:
        assert mgr._rest_timer.isActive()
        assert mgr._rest_timer.interval() == 30 * 60_000
        assert mgr._water_timer.isActive()
        assert mgr._water_timer.interval() == 60 * 60_000
    finally:
        mgr.stop()


def test_health_reminder_emits_and_restarts_only_itself(qapp):
    cfg = _Config(
        {
            "health_cfg": {
                "rest_enabled": True,
                "rest_interval_min": 20,
                "water_enabled": True,
                "water_interval_min": 90,
            }
        }
    )
    mgr = HealthReminderManager(None, cfg)
    events = []
    mgr.rest_due.connect(lambda: events.append("rest"))
    mgr.water_due.connect(lambda: events.append("water"))
    try:
        mgr._on_rest_due()
        assert events == ["rest"]
        assert mgr._rest_timer.isActive()
        assert mgr._rest_timer.interval() == 20 * 60_000
        # 休息触发不应重置喝水倒计时
        assert mgr._water_timer.interval() == 90 * 60_000
    finally:
        mgr.stop()


def test_health_reminder_can_be_disabled(qapp):
    cfg = _Config(
        {
            "health_cfg": {
                "rest_enabled": False,
                "water_enabled": False,
            }
        }
    )
    mgr = HealthReminderManager(None, cfg)
    try:
        assert not mgr._rest_timer.isActive()
        assert not mgr._water_timer.isActive()
    finally:
        mgr.stop()
