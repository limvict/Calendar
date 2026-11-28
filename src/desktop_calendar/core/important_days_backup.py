# coding: utf-8
"""重要日子备份/恢复的纯逻辑：不碰 Qt 控件、不弹窗。"""

import json
from datetime import datetime

from desktop_calendar.config.manager import (
    ConfigManager,
    atomic_write_json,
    get_logger,
)
from desktop_calendar.core.important_days import normalize_important_days

logger = get_logger()
BACKUP_FORMAT_VERSION = 1


class BackupFormatError(ValueError):
    """备份文件结构不符合预期（如缺少 important_days 字段）。"""


class BackupWriteError(OSError):
    """备份文件读取成功，但配置落盘失败（磁盘满 / 权限不足等）。

    继承 OSError 的理由：
      - 语义上"写盘失败"就是 IO 错误，OSError 是最贴切的基类；
      - 历史调用方 / 测试里写 `except OSError` 的路径保持兼容；
      - UI 侧显式 `except BackupWriteError` 优先于 `except OSError`
        匹配（Python 按 except 顺序），仍能拿到专门提示。
    """


def backup_to(path: str, config: ConfigManager) -> int:
    """导出重要日子到 JSON 文件。"""
    raw = config.get("important_days", [])
    if not isinstance(raw, list):
        if raw is not None:
            logger.warning("important_days 类型异常（%s），按空列表导出", type(raw).__name__)
        raw = []
    payload = {
        "version": BACKUP_FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "important_days": raw,
    }
    atomic_write_json(path, payload)
    logger.info("重要日子已备份到 %s，共 %d 条", path, len(raw))
    return len(raw)


def restore_from(path: str, config: ConfigManager) -> tuple:
    """从备份文件恢复重要日子，完全覆盖当前列表。

    异常契约：
      - BackupFormatError：文件读成功但结构不对（缺 important_days）。
      - json.JSONDecodeError / UnicodeDecodeError / OSError：
        读取阶段失败（文件损坏、编码错、权限不足）。
      - BackupWriteError（OSError 子类）：读取 + 归一化成功，但
        配置落盘失败。UI 应显式 `except BackupWriteError` 显示
        "保存配置失败"而非"读取备份失败"。
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        mem_list = data
    elif isinstance(data, dict):
        # 新版字段优先；旧备份（memorial_days）仍可恢复
        mem_list = data.get("important_days", data.get("memorial_days"))
    else:
        mem_list = None
    if not isinstance(mem_list, list):
        raise BackupFormatError("backup file has no important_days list")

    normalized, skipped = normalize_important_days(mem_list)
    if skipped:
        logger.warning("恢复：%d 条归一化失败被跳过（详见 debug 日志）", skipped)

    # 文件里有元素但全部无效：拒绝恢复，避免用空列表覆盖现有数据。
    # 空 list（mem_list == []）是合法的，用户可能确实想清空。
    if mem_list and not normalized:
        raise BackupFormatError(
            f"backup file contains no valid important_days ({skipped}/{len(mem_list)} skipped)"
        )

    # 走原子替换：备份旧值 → 写新值 → flush → 失败回滚 在同一把
    # _flush_lock 下完成，不会被 debounce timer 的 _flush_save 插入。
    try:
        config.replace_key_atomically("important_days", normalized, raise_on_error=True)
    except Exception as e:
        err = BackupWriteError(f"{e}")
        if isinstance(e, OSError):
            err.errno = e.errno
        raise err from e

    logger.info("重要日子已从 %s 恢复，共 %d 条，跳过 %d 条", path, len(normalized), skipped)
    return len(normalized), skipped
