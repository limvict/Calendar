"""Collapsible sidebar card for a random saying."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QLabel,
    QPushButton,
)

from ...config.i18n import tr
from ...config.manager import get_logger
from ...infrastructure.network.sidebar_services import SidebarServices
from ..theme.bundle import LAYOUT
from .sidebar_section import SidebarSection

logger = get_logger()
_REFRESH_INTERVAL = timedelta(days=1)
# 侧边栏可能长期开着，隔一段时间瞄一眼日期，跨天就换一句
_DAY_CHECK_INTERVAL_MS = 15 * 60 * 1000
_ATTRIBUTION_SEP = "\n— "


class SidebarServicesWidget(SidebarSection):
    def __init__(self, source: SidebarServices, parent=None):
        self._source = source
        self._last_request: datetime | None = None
        self._inflight = False
        self._request_generation = 0
        self._stopped = False
        super().__init__(
            "今日灵感",
            object_name="sidebar_services",
            header_name="sidebar_services_header",
            toggle_name="sidebar_services_toggle",
            body_name="sidebar_services_body",
            expanded=False,
            parent=parent,
        )
        # 兼容既有测试/外部引用：折叠开关沿用 _section_button 名字
        self._section_button = self._toggle
        self._section_button.setToolTip("展开 / 收起今日灵感")

        self._header_layout.addStretch(1)
        self._refresh_button = QPushButton("换一句", self._header)
        self._refresh_button.setObjectName("sidebar_services_refresh")
        self._refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_button.setToolTip("换一句今日灵感")
        self._refresh_button.clicked.connect(lambda: self.refresh(force=True))
        self._header_layout.addWidget(self._refresh_button)

        self._body_layout.setContentsMargins(*LAYOUT["saying_body_margins"])
        self._body_layout.setSpacing(LAYOUT["saying_body_spacing"])

        self._quote_label = QLabel("打开侧栏后加载", self._body)
        self._quote_label.setObjectName("sidebar_services_quote")
        self._quote_label.setWordWrap(True)
        self._quote_label.setTextFormat(Qt.TextFormat.PlainText)
        self._quote_label.setMinimumHeight(LAYOUT["saying_quote_min_height"])
        self._quote_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._quote_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # 出处单独一行：比正文弱一档、右对齐，比挤在同一个 label 里清楚
        self._source_label = QLabel(self._body)
        self._source_label.setObjectName("sidebar_services_source")
        self._source_label.setTextFormat(Qt.TextFormat.PlainText)
        self._source_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._source_label.setVisible(False)

        self._body_layout.addWidget(self._quote_label, stretch=1)
        self._body_layout.addWidget(self._source_label)
        self._layout.addStretch(1)
        self._set_expanded(False)

        # 跨天自动刷新（失败不打扰用户，等下次打开或手动刷新）
        self._day_timer = QTimer(self)
        self._day_timer.setInterval(_DAY_CHECK_INTERVAL_MS)
        self._day_timer.timeout.connect(self._refresh_if_new_day)
        self._day_timer.start()

    def _set_expanded(self, checked: bool) -> None:
        super()._set_expanded(checked)
        # 折叠后整行只剩标题，刷新按钮一起收起
        refresh = getattr(self, "_refresh_button", None)
        if refresh is not None:
            refresh.setVisible(checked)

    def apply_theme(self, bundle) -> None:
        self.setStyleSheet(bundle.qss.sidebar_services)
        layout = bundle.layout
        self._quote_label.setMinimumHeight(layout.saying_quote_min_height)
        self._refresh_button.setFixedHeight(layout.saying_refresh_height)
        self._layout.setSpacing(layout.saying_header_spacing)
        self._header_layout.setSpacing(layout.saying_header_spacing)
        self._body_layout.setContentsMargins(*layout.saying_body_margins)
        self._body_layout.setSpacing(layout.saying_body_spacing)

    def _show_quote(self, text: str) -> None:
        quote, _, source = text.partition(_ATTRIBUTION_SEP)
        self._quote_label.setText(quote.strip() or text.strip())
        self._quote_label.setToolTip("")
        source = source.strip()
        self._source_label.setText(f"—— {source}" if source else "")
        self._source_label.setVisible(bool(source))

    def _show_error(self, error: str) -> None:
        # 只给用户可读的结论，原始错误（如 No credentials）进日志/提示，
        # 不直接铺在首屏卡片里。
        logger.info("UAPIS 随机一言暂不可用: %s", error)
        self._quote_label.setText(tr("sidebar.services_unavailable"))
        self._quote_label.setToolTip(tr("sidebar.services_retry_tip"))
        self._source_label.clear()
        self._source_label.setVisible(False)

    def refresh(self, *, force: bool = False) -> None:
        if self._stopped:
            return
        if self._source is None:
            self._quote_label.setText("数据源不可用")
            self._source_label.setVisible(False)
            return
        now = datetime.now()
        if self._inflight and not force:
            return
        if (
            not force
            and self._last_request is not None
            and now - self._last_request < _REFRESH_INTERVAL
        ):
            return
        self._request()

    def _refresh_if_new_day(self) -> None:
        if self._stopped or self._inflight or self._last_request is None:
            return
        if self._last_request.date() < datetime.now().date():
            self.refresh(force=True)

    def _request(self) -> None:
        self._inflight = True
        self._request_generation += 1
        current_gen = self._request_generation
        self._quote_label.setText("正在加载…")
        self._quote_label.setToolTip("")
        self._source_label.setVisible(False)
        self._refresh_button.setDisabled(True)

        def on_success(text: str):
            if current_gen != self._request_generation or self._stopped:
                return
            self._inflight = False
            self._refresh_button.setDisabled(False)
            self._show_quote(text)
            self._last_request = datetime.now()

        def on_error(err: str):
            if current_gen != self._request_generation or self._stopped:
                return
            self._inflight = False
            self._refresh_button.setDisabled(False)
            logger.info("UAPIS 随机一言暂不可用: %s", err)
            self._show_error(err)

        try:
            self._source.fetch(on_success, on_error)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            logger.exception("启动 UAPIS 随机一言请求失败")
            on_error(str(error))

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._inflight = False
        self._day_timer.stop()
        self._refresh_button.setDisabled(False)
        shutdown = getattr(self._source, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def showEvent(self, event):
        super().showEvent(event)
        if self._last_request is None and not self._inflight:
            self.refresh(force=False)
