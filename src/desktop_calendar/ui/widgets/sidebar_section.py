# coding: utf-8
"""可折叠侧栏区块：标题行 + 折叠箭头 + 内容区。

侧栏里的「重要日子」「今日灵感」原本各写了一套相同的 header/body/箭头
逻辑；这里收成一个可复用外壳，子类只往 header/body 里塞自己的控件。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class SidebarSection(QWidget):
    """带可折叠内容区的侧栏区块。

    子类通过 ``_header_layout`` / ``_body_layout`` 追加控件；
    ``_toggle`` 为折叠开关，``_body`` 为内容容器。
    """

    def __init__(
        self,
        title: str,
        *,
        object_name: str,
        header_name: str,
        toggle_name: str,
        body_name: str,
        expanded: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName(object_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._layout = layout

        self._header = QWidget(self)
        self._header.setObjectName(header_name)
        self._header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(2, 0, 0, 4)
        header_layout.setSpacing(6)
        self._header_layout = header_layout

        self._toggle = QToolButton(self._header)
        self._toggle.setObjectName(toggle_name)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.toggled.connect(self._set_expanded)
        header_layout.addWidget(self._toggle)
        layout.addWidget(self._header)

        self._body = QWidget(self)
        self._body.setObjectName(body_name)
        self._body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)
        self._body_layout = body_layout
        layout.addWidget(self._body)
        self._set_expanded(expanded)

    def _set_expanded(self, checked: bool) -> None:
        self._body.setVisible(checked)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
