"""番茄钟专注记录：本地 JSON 持久化，按天聚合。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

from desktop_calendar.config.constants import FOCUS_LOG_FILE_NAME
from desktop_calendar.config.manager import atomic_write_json, get_logger
from desktop_calendar.utils.paths import get_app_data_dir

logger = get_logger()

# 历史版本的专注时间秒字段曾被写成 3 位（如 08:28:199，疑似微秒被截断后拼上），
# 加载时截回 2 位，既救回这条记录，也能在回写后让旧版本正常读取。
_LEGACY_SECONDS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(\d+)$")


def _normalize_started_at(value: object) -> tuple[object, bool]:
    """返回 (归一化后的值, 是否发生了修复)。"""
    if not isinstance(value, str):
        return value, False
    match = _LEGACY_SECONDS_RE.fullmatch(value)
    if match is None:
        return value, False
    return match.group(1), True


@dataclass
class FocusRecord:
    date: str  # YYYY-MM-DD
    started_at: str  # ISO 时间
    minutes: int
    title: str = ""
    schedule_id: str = ""

    def __post_init__(self) -> None:
        try:
            parsed_date = date.fromisoformat(self.date)
            started = datetime.fromisoformat(self.started_at)
        except (TypeError, ValueError) as error:
            raise ValueError("专注记录日期或开始时间无效") from error
        if parsed_date.isoformat() != self.date or started.date() != parsed_date:
            raise ValueError("专注记录日期必须与开始时间一致")
        if not isinstance(self.minutes, int) or isinstance(self.minutes, bool) or self.minutes <= 0:
            raise ValueError("专注分钟数必须为正整数")
        if not isinstance(self.title, str) or not isinstance(self.schedule_id, str):
            raise ValueError("专注标题和日程编号必须为文本")


def _default_path() -> str:
    return os.path.join(get_app_data_dir(), FOCUS_LOG_FILE_NAME)


class FocusLog:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or _default_path()
        self._records: list[FocusRecord] = []
        # 无法解析的原始条目：原样保留在文件里，避免自愈时误删用户数据
        self._invalid: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("读取专注记录失败: %s", self._path, exc_info=True)
            return
        records = data.get("records") if isinstance(data, dict) else None
        if not isinstance(records, list):
            logger.warning("专注记录文件结构异常: %s", self._path)
            return

        repaired = 0
        skipped = 0
        for item in records:
            if not isinstance(item, dict):
                logger.debug("跳过非对象专注记录: %r", item)
                skipped += 1
                continue
            payload = dict(item)
            payload["started_at"], fixed = _normalize_started_at(payload.get("started_at"))
            try:
                self._records.append(FocusRecord(**payload))
            except (TypeError, ValueError):
                # 单条坏记录只记 debug（含堆栈），不刷 WARNING 堆栈；末尾汇总一条即可
                logger.debug("跳过无效专注记录: %r", item, exc_info=True)
                self._invalid.append(item)
                skipped += 1
                continue
            repaired += int(fixed)

        if skipped:
            logger.warning("跳过 %d 条无效专注记录: %s", skipped, self._path)
        if repaired:
            logger.info("修复 %d 条专注记录的历史时间格式: %s", repaired, self._path)
            try:
                self._save()
            except Exception:
                logger.warning("回写修复后的专注记录失败: %s", self._path, exc_info=True)

    def _save(self) -> None:
        records = [asdict(r) for r in self._records]
        # 坏条目原样写回：它们不参与统计，但也不该被静默删除
        records.extend(self._invalid)
        atomic_write_json(self._path, {"version": 1, "records": records}, protect=True)

    def add(
        self,
        minutes: int,
        title: str = "",
        schedule_id: str = "",
        started_at: datetime | None = None,
    ) -> FocusRecord:
        started = started_at or datetime.now()
        record = FocusRecord(
            date=started.date().isoformat(),
            started_at=started.isoformat(timespec="seconds"),
            minutes=minutes,
            title=title,
            schedule_id=schedule_id,
        )
        previous = list(self._records)
        self._records.append(record)
        try:
            self._save()
        except Exception:
            self._records = previous
            raise
        return record

    def today_count(self, today: date | None = None) -> int:
        key = (today or date.today()).isoformat()
        return sum(1 for r in self._records if r.date == key)

    def today_minutes(self, today: date | None = None) -> int:
        key = (today or date.today()).isoformat()
        return sum(r.minutes for r in self._records if r.date == key)

    def recent(self, days: int = 7, today: date | None = None) -> list[tuple[date, int, int]]:
        """返回最近 N 天 (日期, 次数, 分钟)，旧→新。"""
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise ValueError("天数必须为非负整数")
        today = today or date.today()
        buckets: dict[str, list[FocusRecord]] = {}
        for r in self._records:
            buckets.setdefault(r.date, []).append(r)
        out = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            items = buckets.get(d.isoformat(), [])
            out.append((d, len(items), sum(x.minutes for x in items)))
        return out
