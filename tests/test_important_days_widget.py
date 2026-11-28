# coding: utf-8
"""侧栏重要日子卡片控件：卡片数量、置顶顺序、点击跳转与空状态。"""

from datetime import date

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton

from desktop_calendar.config.constants import DEFAULT_THEME
from desktop_calendar.core.important_days import (
    build_important_day_cards,
    get_next_important_day_date,
)
from desktop_calendar.ui.theme import build_bundle
from desktop_calendar.ui.widgets import ImportantDaysWidget


@pytest.fixture
def bundle(qapp):
    return build_bundle("light", dict(DEFAULT_THEME))


def _mem(**kwargs):
    base = {
        "name": "重要日子",
        "type": "solar",
        "month": 1,
        "day": 1,
        "repeat_type": "year",
        "enabled": True,
        "advance_days": 0,
    }
    base.update(kwargs)
    return base


def _cards(widget):
    return widget.findChildren(QFrame, "important_day_card")


class TestCardsWidget:
    def test_renders_one_card_per_enabled_item(self, qapp, qtbot, bundle):
        widget = ImportantDaysWidget(
            [
                _mem(name="A", month=3, day=1),
                _mem(name="B", month=4, day=1),
                _mem(name="C", enabled=False),
            ]
        )
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        widget.show()
        assert len(_cards(widget)) == 2

    def test_pinned_card_first(self, qapp, qtbot, bundle):
        widget = ImportantDaysWidget(
            [
                _mem(name="普通", month=2, day=1),
                _mem(name="置顶", month=12, day=1, pinned=True),
            ]
        )
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        widget.show()
        cards = _cards(widget)
        assert "置顶" in cards[0].toolTip()
        assert "普通" in cards[1].toolTip()

    def test_click_emits_next_date(self, qapp, qtbot, bundle):
        mem = _mem(name="生日", month=5, day=20)
        expected = get_next_important_day_date(mem, date.today(), include_base=True)
        widget = ImportantDaysWidget([mem])
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        widget.show()
        qtbot.wait(10)
        card = _cards(widget)[0]
        with qtbot.waitSignal(widget.activated, timeout=1000) as blocker:
            qtbot.mouseClick(card, Qt.MouseButton.LeftButton, pos=card.rect().center())
        emitted = blocker.args[0]
        assert (emitted.year(), emitted.month(), emitted.day()) == (
            expected.year,
            expected.month,
            expected.day,
        )

    def test_empty_state(self, qapp, qtbot, bundle):
        widget = ImportantDaysWidget([])
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        assert widget._count_label.text() == ""
        labels = [label.text() for label in widget.findChildren(QLabel)]
        assert "还没有重要日子" in labels
        buttons = [button.text() for button in widget.findChildren(QPushButton)]
        assert "添加重要日子" in buttons

    def test_all_disabled_state(self, qapp, qtbot, bundle):
        widget = ImportantDaysWidget([_mem(name="停用", enabled=False)])
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        labels = [label.text() for label in widget.findChildren(QLabel)]
        assert "重要日子都已停用" in labels

    def test_more_button_when_over_limit(self, qapp, qtbot, bundle):
        mems = [_mem(name=f"m{i}", month=i + 1, day=1) for i in range(6)]
        widget = ImportantDaysWidget(mems)
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        assert len(_cards(widget)) == 4
        more = [b for b in widget.findChildren(QPushButton) if "查看" in b.text()]
        assert len(more) == 1

    def test_set_important_days_replaces_cards(self, qapp, qtbot, bundle):
        widget = ImportantDaysWidget([_mem(name="A")])
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        widget.set_important_days([_mem(name="B"), _mem(name="C")])
        assert len(_cards(widget)) == 2
        assert widget._count_label.text() == "共2条"

    def test_cards_sorted_by_days_remaining(self, qapp, qtbot, bundle):
        widget = ImportantDaysWidget(
            [_mem(name="远", month=6, day=1), _mem(name="近", month=12, day=1)]
        )
        qtbot.addWidget(widget)
        widget.apply_theme(bundle)
        cards = build_important_day_cards(widget._important_days, widget._today)
        assert cards[0].days <= cards[1].days
