# coding: utf-8
"""快捷侧栏：显隐切换、宽度重算与入口按钮分发。"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QApplication,
)

from desktop_calendar.utils.logging_setup import APP_LOGGER_NAME

from .helpers import _screen_ui_scale

logger = logging.getLogger(APP_LOGGER_NAME)


class MainWindowSidebarMixin:
    """快捷侧栏：显隐切换、宽度重算与入口按钮分发。"""

    def _toggle_sidebar(self, visible: bool) -> None:
        self._sidebar_visible = visible
        self.sidebar.setVisible(visible)
        self.btn_sidebar.setToolTip("关闭快捷侧边栏" if visible else "打开快捷侧边栏")
        screen = self.windowHandle().screen() if self.windowHandle() is not None else None
        if screen is None:
            screen = QApplication.screenAt(self.frameGeometry().center())
        # 抽屉覆盖在主窗体上，展开/收起不再改变窗口尺寸，也不重算 UI 缩放
        self.theme_mgr.set_ui_scale(_screen_ui_scale(screen))
        self._apply_theme_geometry(self.theme_mgr.current)
        self._refresh_styles(self.theme_mgr.current)
        # _apply_theme_geometry 会把信息栏重置为主题上限，这里按实际行数收回
        self._refresh_info_label()
        if visible:
            self.sidebar.raise_()
            self.important_days.refresh_if_new_day()
            self.sidebar_services_widget.refresh()
        if screen is not None:
            available = screen.availableGeometry()
            right = max(available.left(), available.right() - self.width() + 1)
            self.move(
                max(available.left(), min(self.x(), right)),
                max(available.top(), min(self.y(), available.bottom() - self.height() + 1)),
            )

    def _run_sidebar_action(self, action) -> None:
        if self._sidebar_visible:
            self.btn_sidebar.setChecked(False)
        action()
