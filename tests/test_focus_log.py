# coding: utf-8
"""focus_log：写入格式、历史坏秒字段自愈、无效条目保留。"""

import json
import os
from datetime import date, datetime

from desktop_calendar.core.focus_log import FocusLog


def _write(path, records):
    path.write_text(
        json.dumps({"version": 1, "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )


def _read_records(path):
    return json.loads(path.read_text(encoding="utf-8"))["records"]


def test_add_writes_seconds_only_isoformat(tmp_path):
    """新记录必须是 19 字符的秒级 ISO，不能再出现 08:28:199 这种多余数字。"""
    path = tmp_path / "focus_log.json"
    log = FocusLog(str(path))

    record = log.add(25, started_at=datetime(2026, 11, 19, 8, 28, 19, 900000))

    assert record.started_at == "2026-11-19T08:28:19"
    assert _read_records(path)[0]["started_at"] == "2026-11-19T08:28:19"
    assert FocusLog(str(path)).today_minutes(date(2026, 11, 19)) == 25


def test_load_salvages_three_digit_seconds(tmp_path):
    """历史坏值 08:28:199 → 08:28:19，记录保留且文件被回写修复。"""
    path = tmp_path / "focus_log.json"
    _write(
        path,
        [{"date": "2026-11-19", "started_at": "2026-11-19T08:28:199", "minutes": 25}],
    )

    log = FocusLog(str(path))

    assert log.today_count(date(2026, 11, 19)) == 1
    assert log.today_minutes(date(2026, 11, 19)) == 25
    # 回写后旧版本（不支持自愈）也能正常读取
    assert _read_records(path)[0]["started_at"] == "2026-11-19T08:28:19"


def test_load_salvages_space_separator_variant(tmp_path):
    path = tmp_path / "focus_log.json"
    _write(
        path,
        [{"date": "2026-11-19", "started_at": "2026-11-19 08:28:199", "minutes": 25}],
    )

    log = FocusLog(str(path))

    assert log.today_minutes(date(2026, 11, 19)) == 25
    assert _read_records(path)[0]["started_at"] == "2026-11-19 08:28:19"


def test_load_skips_bad_record_but_keeps_it_on_save(tmp_path):
    path = tmp_path / "focus_log.json"
    good = {"date": "2026-11-19", "started_at": "2026-11-19T09:00:00", "minutes": 25}
    bad = {"date": "2026-11-19", "started_at": "昨天下午", "minutes": 25}
    _write(path, [good, bad])

    log = FocusLog(str(path))
    assert log.today_count(date(2026, 11, 19)) == 1

    log.add(5, started_at=datetime(2026, 11, 19, 10, 0))
    stored = _read_records(path)
    assert len(stored) == 3
    assert bad in stored, "无法解析的条目只应跳过统计，不能被静默删除"


def test_date_mismatch_record_is_skipped(tmp_path):
    path = tmp_path / "focus_log.json"
    _write(
        path,
        [{"date": "2026-11-19", "started_at": "2026-11-20T08:28:19", "minutes": 25}],
    )
    assert FocusLog(str(path)).today_count(date(2026, 11, 19)) == 0


def test_salvaged_file_stays_read_only(tmp_path):
    path = tmp_path / "focus_log.json"
    _write(
        path,
        [{"date": "2026-11-19", "started_at": "2026-11-19T08:28:199", "minutes": 25}],
    )

    FocusLog(str(path))

    assert os.access(path, os.W_OK) is False, "自愈回写后应重新置为只读"
